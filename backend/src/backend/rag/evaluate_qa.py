"""End-to-end RAG evaluation on a labelled Q&A set (tests/rag/dataset_eval.json).

    uv run python -m backend.rag.evaluate_qa                      # full run
    uv run python -m backend.rag.evaluate_qa --only q03,q41       # a few items
    uv run python -m backend.rag.evaluate_qa --k 6                # try another top-k

Every question goes through the SAME path as the website chat:
    classifier (route + standalone search_query) -> search_kb (Chroma, threshold)
    -> answer prompt (or the "I'm not sure" reply) ; nothing is sent anywhere.

Metrics
  Retrieval (answerable items, top-k before the threshold):
    source_hit@k   any retrieved chunk comes from an expected source file
    source_recall  share of expected source files retrieved (matters for multi-chunk items)
    MRR            1 / rank of the first chunk from an expected source
    fact_recall    share of must_include facts present in the retrieved text
                   (facts that exist nowhere in the KB, e.g. computed totals, are excluded)
    empty_after_threshold   no passage survived KB_MIN_SCORE (the bot will say "not sure")
  Answer (answerable items):
    must_include   share of must_include facts present in the answer (exact, normalised)
    correctness    LLM judge vs the reference answer: 1 / 0.5 / 0
    faithfulness   LLM judge: every claim is supported by the retrieved passages (1/0)
    false_refusal  answered "not sure" although the KB has the answer
  Abstention (unanswerable items):
    abstain_ok     judge: did not invent the missing information and said it is not available
  Routing:
    route_ok       the classifier sends the question to the knowledge base (intent=question)

Outputs: knowledge/mdcold/build/eval_qa_report.md and eval_qa_results.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage

from backend.config import PROJECT_ROOT, get_settings
from backend.graphs.run_a_chat.deps import RunADeps, analyze, answer
from backend.graphs.run_a_chat.nodes import RunANodes, answer_context, dont_know
from backend.rag.retriever import search_kb_multi
from backend.rag.vectorstore import get_collection

DATASET = PROJECT_ROOT / "tests" / "rag" / "dataset_eval.json"
NUM_WORDS = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "15": "fifteen", "20": "twenty"}


# --- normalisation & exact-fact matching ------------------------------------------------

def norm(text: str) -> str:
    text = text.lower().replace("**", "").replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace(" ", " ")
    return re.sub(r"\s+", " ", text)


def has_fact(text: str, fact: str) -> bool:
    t, f = norm(text), norm(fact)
    if f in t:
        return True
    digits = re.sub(r"\D", "", f)
    if len(digits) >= 10:                                   # phone numbers in any format
        return digits in re.sub(r"\D", "", t)
    if f in NUM_WORDS and re.search(rf"\b({re.escape(f)}|{NUM_WORDS[f]})\b", t):
        return True
    if f.endswith("s") and f[:-1] in t:                     # 'multiple indoor units' vs 'unit'
        return True
    return False


# --- LLM judge ----------------------------------------------------------------------------

class Verdict(BaseModel):
    correctness: float = Field(description="1 = matches the reference, 0.5 = partly, 0 = wrong or missing")
    faithful: bool = Field(description="every factual claim in the answer is supported by the passages")
    unsupported_claims: list[str]
    abstained: bool = Field(description="the answer says the information is not available / not sure")
    invented_missing_info: bool = Field(description="the answer states a specific value the KB lacks")
    reason: str


JUDGE_PROMPT = """You grade a customer-support chatbot for an HVAC business. Be strict and literal.

Question: {question}
Answerable from the knowledge base: {answerable}
Reference answer (ground truth): {reference}

Retrieved passages the chatbot saw:
<passages>
{passages}
</passages>

Chatbot answer:
<answer>
{answer}
</answer>

Grade:
- correctness: 1 if the answer gives the reference's key facts correctly (wording may differ; extra correct
  detail is fine); 0.5 if partly correct or missing a key fact; 0 if wrong, contradicting, or a refusal when
  the reference has the answer. For an UNANSWERABLE question, 1 if the answer says the information is not
  available (and may offer to call or book) without inventing it, else 0.
- faithful: true only if every factual claim in the answer is supported by the passages (simple arithmetic
  on passage numbers counts as supported). List unsupported claims.
- abstained: true if the answer says it does not know / the information is not stated.
- invented_missing_info: true if the answer states a specific value (price, rate, date, name, policy) that
  the reference says is not available.
- reason: one short sentence.
"""


def judge(llm, item: dict, passages: str, reply: str) -> Verdict:
    prompt = JUDGE_PROMPT.format(question=item["question"], answerable=item["answerable"],
                                 reference=item["reference_answer"], passages=passages or "(none)",
                                 answer=reply)
    return llm.invoke(prompt)


# --- one item -------------------------------------------------------------------------------

def run_item(item: dict, k: int, judge_llm, kb_text: str) -> dict:
    s = get_settings()
    out = {"id": item["id"], "question": item["question"], "category": item["category"],
           "style": item.get("style"), "answerable": item["answerable"],
           "multi_chunk": item.get("multi_chunk", False)}
    t0 = time.perf_counter()
    a = analyze(item["question"], "(none)", "No booking in progress.")
    out["intent"] = a.intent
    out["route_ok"] = a.intent == "question"
    query = a.search_query or item["question"]
    queries = [query] + [q for q in a.sub_queries if q][:2]
    out["search_query"] = " | ".join(queries)

    t1 = time.perf_counter()
    ranked = search_kb_multi(queries, k=k, min_score=-1.0)        # same selection, no threshold
    out["retrieval_ms"] = round((time.perf_counter() - t1) * 1000)
    # Answer through the REAL rag_answer node; record exactly which passages it used.
    used: list = []

    def recording_search(qs):
        found = search_kb_multi(qs, k=k)
        used.extend(found)
        return found

    t2 = time.perf_counter()
    deps = RunADeps(analyze=None, search=recording_search, answer=answer, smalltalk=None, get_slots=None,
                    create_booking=None, change_booking=None, create_needs_person_case=None,
                    send_confirmation=None, post_booking=None, post_needs_person=None, post_urgent=None)
    state = {"messages": [HumanMessage(content=item["question"])], "analysis": a.model_dump()}
    reply = RunANodes(deps).rag_answer(state)["reply"]
    out["answer_ms"] = round((time.perf_counter() - t2) * 1000)
    kept = used
    kept_ids = {p.id for p in kept}
    out["retrieved"] = [{"id": p.id, "source": p.source, "score": p.score, "kept": p.id in kept_ids}
                        for p in ranked]
    expected = set(item.get("expected_sources") or [])
    sources = [p.source for p in ranked]
    rank = next((i for i, src in enumerate(sources, 1) if src in expected), None)
    out["source_hit"] = rank is not None
    out["rr"] = 1 / rank if rank else 0.0
    out["source_recall"] = (len(expected & set(sources)) / len(expected)) if expected else None
    out["empty_after_threshold"] = not kept
    out["top_score"] = ranked[0].score if ranked else 0.0

    context = answer_context(kept) if kept else ""          # exactly what the answer step saw
    facts = item.get("must_include") or []
    in_kb = [f for f in facts if has_fact(kb_text, f)]
    out["derived_facts"] = [f for f in facts if f not in in_kb]
    out["fact_recall"] = (sum(has_fact(context, f) for f in in_kb) / len(in_kb)) if in_kb else None

    out["total_ms"] = round((time.perf_counter() - t0) * 1000)
    out["answer"] = reply
    out["refused"] = reply == dont_know() or bool(re.search(r"not sure|don't have that information|not stated", reply, re.I))
    out["must_include"] = (sum(has_fact(reply, f) for f in facts) / len(facts)) if facts else None
    out["missing_facts"] = [f for f in facts if not has_fact(reply, f)]

    v = judge(judge_llm, item, context, reply)
    out.update(correctness=v.correctness, faithful=v.faithful, unsupported_claims=v.unsupported_claims,
               abstained=v.abstained, invented=v.invented_missing_info, judge_reason=v.reason,
               judge_correctness=v.correctness)
    if item["answerable"]:
        # The generic "I'm not sure" reply on an answerable item is a failure, even when the judge
        # is fooled (it contains the phone number, so "what's your phone?" looks answered).
        generic = reply == dont_know()
        out["false_refusal"] = generic or (out["refused"] and v.correctness == 0)
        if generic:
            out["correctness"] = 0.0
            out["judge_reason"] = "generic 'not sure' reply on an answerable question (judge said: " + v.reason + ")"
    else:
        out["abstain_ok"] = v.correctness >= 1 and not v.invented_missing_info
    return out


# --- aggregation & report ------------------------------------------------------------------

def mean(values) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def pct(v) -> str:
    return "—" if v is None else f"{v:.0%}"


def summarize(rows: list[dict]) -> dict:
    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]
    return {
        "n": len(rows), "answerable": len(ans), "unanswerable": len(una),
        "route_ok": mean(r["route_ok"] for r in rows),
        "source_hit@k": mean(r["source_hit"] for r in ans),
        "source_recall": mean(r["source_recall"] for r in ans),
        "mrr": mean(r["rr"] for r in ans),
        "fact_recall": mean(r["fact_recall"] for r in ans),
        "empty_after_threshold": mean(r["empty_after_threshold"] for r in ans),
        "must_include": mean(r["must_include"] for r in ans),
        "correctness": mean(r["correctness"] for r in ans),
        "faithfulness": mean(r["faithful"] for r in rows),
        "false_refusal": mean(r["false_refusal"] for r in ans),
        "abstain_ok": mean(r["abstain_ok"] for r in una),
        "invented_on_unanswerable": mean(r["invented"] for r in una),
        "p50_ms": statistics.median(r["total_ms"] for r in rows),
        "p95_ms": sorted(r["total_ms"] for r in rows)[max(0, int(len(rows) * 0.95) - 1)],
    }


def breakdown(rows: list[dict], key: str) -> list[tuple[str, int, dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r[key])].append(r)
    out = []
    for name, rs in sorted(groups.items()):
        ans = [r for r in rs if r["answerable"]]
        una = [r for r in rs if not r["answerable"]]
        out.append((name, len(rs), {
            "hit": mean(r["source_hit"] for r in ans), "facts": mean(r["must_include"] for r in ans),
            "correct": mean(r["correctness"] for r in ans), "abstain": mean(r["abstain_ok"] for r in una),
            "faithful": mean(r["faithful"] for r in rs)}))
    return out


def is_failure(r: dict) -> bool:
    if not r["answerable"]:
        return not r.get("abstain_ok") or not r["faithful"]
    return r["correctness"] < 1 or (r["must_include"] or 1) < 1 or not r["faithful"] or not r["route_ok"]


def write_report(path: Path, rows: list[dict], summary: dict, k: int) -> None:
    s = get_settings()
    L = ["# RAG evaluation report", "",
         f"Dataset: `tests/rag/dataset_eval.json` ({summary['n']} items: {summary['answerable']} answerable, "
         f"{summary['unanswerable']} unanswerable). Chat model `{s.llm_model}`, judge `{s.rag_report_model}`, "
         f"embeddings `{s.rag_embedding_model}`, top-k {k}, KB_MIN_SCORE {s.kb_min_score}.", "",
         "## Scorecard", "", "| Metric | Score | Meaning |", "|---|---|---|"]
    rowsdef = [
        ("Routing: goes to the knowledge base", "route_ok", "classifier picks intent=question"),
        ("Retrieval: source hit@k", "source_hit@k", "an expected source file is in the top-k"),
        ("Retrieval: source recall", "source_recall", "share of expected source files retrieved"),
        ("Retrieval: MRR", "mrr", "1/rank of the first relevant chunk"),
        ("Retrieval: fact recall", "fact_recall", "must-include facts present in the passages used"),
        ("Retrieval: nothing above threshold", "empty_after_threshold", "lower is better"),
        ("Answer: must-include facts", "must_include", "exact facts present in the answer"),
        ("Answer: correctness (judge)", "correctness", "vs reference answer"),
        ("Answer: faithfulness (judge)", "faithfulness", "no claims beyond the passages"),
        ("Answer: false refusals", "false_refusal", "said 'not sure' although answerable; lower is better"),
        ("Abstention: correct refusals", "abstain_ok", "unanswerable items handled without inventing"),
        ("Abstention: invented facts", "invented_on_unanswerable", "lower is better"),
    ]
    for label, key, meaning in rowsdef:
        val = summary[key]
        L.append(f"| {label} | {'—' if val is None else (f'{val:.3f}' if key == 'mrr' else pct(val))} | {meaning} |")
    L += [f"| Latency p50 / p95 | {summary['p50_ms']} ms / {summary['p95_ms']} ms | classifier + search + answer |", ""]

    for key, title in (("category", "By category"), ("style", "By question style"), ("multi_chunk", "Multi-chunk")):
        L += [f"## {title}", "", "| Group | n | hit@k | facts | correct | abstain | faithful |", "|---|---|---|---|---|---|---|"]
        for name, n, m in breakdown(rows, key):
            L.append(f"| {name} | {n} | {pct(m['hit'])} | {pct(m['facts'])} | {pct(m['correct'])} | "
                     f"{pct(m['abstain'])} | {pct(m['faithful'])} |")
        L.append("")

    fails = [r for r in rows if is_failure(r)]
    L += [f"## Failures ({len(fails)})", ""]
    for r in fails:
        got = ", ".join(f"{x['id']} ({x['score']:.2f}{'' if x['kept'] else ', dropped'})" for x in r["retrieved"])
        L += [f"### {r['id']} · {r['category']} · {r['style']} — {r['question']}", "",
              f"- route: `{r['intent']}`" + ("" if r["route_ok"] else " **(would not reach the KB in chat)**"),
              f"- search query: {r['search_query']}",
              f"- retrieved: {got}",
              f"- answer: {r['answer']}",
              f"- correctness {r['correctness']} · faithful {r['faithful']} · missing facts {r['missing_facts'] or '—'}"
              + (f" · unsupported {r['unsupported_claims']}" if r["unsupported_claims"] else ""),
              f"- judge: {r['judge_reason']}", ""]
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default=str(DATASET))
    p.add_argument("--k", type=int, default=get_settings().kb_top_k)
    p.add_argument("--only", default="", help="comma-separated item ids")
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args(argv)

    s = get_settings()
    items = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        items = [i for i in items if i["id"] in wanted]
    kb_text = "\n".join(get_collection().get(include=["documents"])["documents"])
    judge_llm = ChatOpenAI(model=s.rag_report_model, temperature=0, api_key=s.openai_api_key
                           ).with_structured_output(Verdict, method="json_schema", strict=True)

    print(f"evaluating {len(items)} items (k={args.k}, threshold={s.kb_min_score}) ...", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda it: run_item(it, args.k, judge_llm, kb_text), items))

    summary = summarize(rows)
    build = s.kb_build_dir
    write_report(build / "eval_qa_report.md", rows, summary, args.k)
    (build / "eval_qa_results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")

    width = max(len(k) for k in summary)
    for key, val in summary.items():
        shown = val if isinstance(val, (int, str)) or val is None else (f"{val:.3f}" if key == "mrr" or key.endswith("_ms") else f"{val:.0%}")
        print(f"  {key:<{width}}  {shown}")
    print(f"\nfailures: {sum(is_failure(r) for r in rows)}  ->  {build / 'eval_qa_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
