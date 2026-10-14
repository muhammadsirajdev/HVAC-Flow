"""Everything Run A calls outside itself, behind one object so tests can swap in fakes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from langchain_core.messages import AnyMessage
from langchain_core.tools import BaseTool

from backend.config import get_settings
from backend.core.timeutil import business_tz, now
from backend.graphs.common.llm import get_chat_llm, load_prompt, structured
from backend.graphs.run_a_chat.schemas import SERVICES, TurnAnalysis

PROMPTS = Path(__file__).parent / "prompts"
log = logging.getLogger(__name__)


def _fill(template: str, **values: str) -> str:
    for key, val in values.items():          # plain replace: customer text may contain braces
        template = template.replace("{" + key + "}", val)
    return template


def format_history(messages: list[AnyMessage], last: int = 8) -> str:
    lines = []
    for m in messages[-last:]:
        who = "Customer" if m.type == "human" else "Assistant"
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines) or "(none)"


@dataclass
class RunADeps:
    analyze: Callable[[str, str, str], TurnAnalysis]         # (message, history, booking_context)
    search: Callable[[list[str]], list]                      # queries -> list[Passage]
    answer: Callable[[str, str, str], str]                   # (question, passages, history)
    smalltalk: Callable[[str, str], str]                     # (message, booking_note)
    get_slots: Callable[..., list]                           # booking.get_open_slots
    create_booking: Callable                                 # booking.create_booking
    change_booking: Callable                                 # booking.change_booking (same session only)
    create_needs_person_case: Callable                       # booking.create_needs_person_case
    send_confirmation: Callable                              # notify.send_booking_confirmation
    post_booking: Callable
    post_needs_person: Callable
    post_urgent: Callable
    # MCP tools loaded from Klavis (gmail_send_email, slack_user_post_message,
    # slack_user_list_channels). The notify/guard nodes execute them via the notify functions.
    mcp_tools: dict[str, BaseTool] = field(default_factory=dict)
    load_booking: Callable = lambda case_id: None           # booking.load_booking
    # (task, facts, fallback, message, history) -> natural wording; tests keep the fallback
    phrase: Callable = lambda task, facts, fallback, message, history: fallback
    send_pending: Callable = lambda stored, tools=None: {}  # notify.send_pending


# --- real implementations ---------------------------------------------------------

def analyze(message: str, history: str, booking_context: str) -> TurnAnalysis:
    s = get_settings()
    today = now()
    prompt = _fill(load_prompt(PROMPTS / "classify.md"), business=s.business_name,
                   today=f"{today:%A %Y-%m-%d}", timezone=str(business_tz()),
                   services=", ".join(SERVICES), booking_context=booking_context,
                   history=history, message=message)
    return structured(TurnAnalysis).invoke(prompt)


def answer(question: str, passages: str, history: str) -> str:
    s = get_settings()
    prompt = _fill(load_prompt(PROMPTS / "answer.md"), business=s.business_name,
                   phone=s.business_phone, passages=passages, history=history, question=question)
    return str(get_chat_llm().invoke(prompt).content).strip()


def smalltalk(message: str, booking_note: str) -> str:
    s = get_settings()
    prompt = _fill(load_prompt(PROMPTS / "smalltalk.md"), business=s.business_name,
                   booking_note=booking_note, message=message)
    return str(get_chat_llm(0.3).invoke(prompt).content).strip()


def phrase(task: str, facts: str, fallback: str, message: str, history: str) -> str:
    """Word a code-decided message like a human receptionist. Falls back to the template
    if the model fails or adds anything (numbers, prices) that the task did not contain."""
    s = get_settings()
    prompt = _fill(load_prompt(PROMPTS / "reply_writer.md"), business=s.business_name, task=task,
                   facts=facts or "(none)", history=history, message=message)
    try:
        text = str(get_chat_llm(0.4).invoke(prompt).content).strip().strip('"')
    except Exception:
        log.exception("reply writer failed; using template")
        return fallback
    return text if _safe_wording(text, f"{task} {facts} {fallback} {message} {s.business_phone}") else fallback


def _safe_wording(text: str, allowed: str) -> bool:
    """The writer may rephrase, never add facts: every number in the text must be in `allowed`."""
    import re
    if not text or len(text) > 400 or "$" in text and "$" not in allowed:
        return False
    digits_allowed = re.sub(r"\D", " ", allowed).split()
    for num in re.findall(r"\d+", text):
        if not any(num in d for d in digits_allowed):
            return False
    return True


def search(queries: list[str] | str) -> list:
    from backend.rag import search_kb_multi   # lazy: chromadb is only needed for questions
    return search_kb_multi([queries] if isinstance(queries, str) else queries)


def load_mcp_tools() -> dict[str, BaseTool]:
    """Fetch the required tools from the Klavis MCP servers (once per process)."""
    from backend.mcp.client import get_tool_map
    try:
        tools = get_tool_map()
        log.info("Run A got MCP tools: %s", sorted(tools))
        return tools
    except Exception:
        log.exception("could not load MCP tools; notifications will retry loading on use")
        return {}


def default_deps() -> RunADeps:
    from backend.tools import booking, notify
    return RunADeps(
        analyze=analyze, search=search, answer=answer, smalltalk=smalltalk,
        get_slots=booking.get_open_slots, create_booking=booking.create_booking,
        change_booking=booking.change_booking,
        create_needs_person_case=booking.create_needs_person_case,
        send_confirmation=notify.send_booking_confirmation, post_booking=notify.post_booking,
        post_needs_person=notify.post_needs_person, post_urgent=notify.post_urgent,
        mcp_tools=load_mcp_tools(),
        load_booking=booking.load_booking, send_pending=notify.send_pending, phrase=phrase,
    )
