import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getActivity, getCases, getOverview, getSchedule } from "../api";
import { ActivityFeed } from "../components/ActivityFeed";
import { CaseList } from "../components/CaseList";
import { DispatchBoard } from "../components/DispatchBoard";
import { Schedule } from "../components/Schedule";
import { WorkOrder } from "../components/WorkOrder";
import { setBusinessTz } from "../lib/format";
import { usePoll } from "../lib/hooks";

type Tab = "cases" | "schedule" | "activity";
const TABS: { id: Tab; label: string }[] = [
  { id: "cases", label: "Cases" },
  { id: "schedule", label: "Schedule" },
  { id: "activity", label: "Activity" },
];

export default function Office() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "cases";
  const caseId = Number(params.get("case")) || null;
  const status = params.get("status") || "";
  const channel = params.get("channel") || "";
  const [query, setQuery] = useState(params.get("q") || "");
  const [q, setQ] = useState(query);

  useEffect(() => {
    const id = window.setTimeout(() => setQ(query.trim()), 250);
    return () => window.clearTimeout(id);
  }, [query]);

  const update = (changes: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, String(v));
    }
    // Opening a case or a tab is a step the back button should undo; filters and typing are not.
    setParams(next, { replace: !("case" in changes) && !("tab" in changes) });
  };

  const overview = usePoll(getOverview, 10000);
  const cases = usePoll(() => getCases({ status, channel, q }), 8000, [status, channel, q], tab === "cases");
  const activity = usePoll(() => getActivity(80), 8000, [], tab === "activity");
  const schedule = usePoll(() => getSchedule(7), 15000, [], tab === "schedule");

  useEffect(() => {
    if (overview.data) setBusinessTz(overview.data.business.tz);
  }, [overview.data]);

  useEffect(() => {
    document.title = caseId ? `Case ${caseId} | MD Cold office` : "Office | MD Cold Services";
  }, [caseId]);

  const openCase = (id: number) => update({ tab: "cases", case: id });

  return (
    <div className="office">
      <DispatchBoard
        data={overview.data}
        error={overview.error}
        onNeedsPerson={() => update({ tab: "cases", status: "needs_person", case: null })}
        onSchedule={() => update({ tab: "schedule" })}
        onCase={openCase}
      />

      <div className="office__bar">
        <div className="tabs" role="tablist" aria-label="Office views">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              className="tabs__tab"
              onClick={() => update({ tab: t.id === "cases" ? null : t.id })}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="office__live" aria-live="polite">
          Updates on its own every few seconds
        </p>
      </div>

      {tab === "cases" && (
        <div className={caseId ? "desk desk--open" : "desk"}>
          <CaseList
            rows={cases.data?.cases ?? null}
            error={cases.error}
            counts={overview.data?.by_status}
            status={status}
            channel={channel}
            query={query}
            selected={caseId}
            onQuery={(v) => {
              setQuery(v);
              update({ q: v || null });
            }}
            onStatus={(s) => update({ status: s || null })}
            onChannel={(c) => update({ channel: c || null })}
            onSelect={openCase}
          />
          <section className="desk__detail" aria-label="Case details">
            {caseId ? (
              <WorkOrder caseId={caseId} onClose={() => update({ case: null })} onCase={openCase} />
            ) : (
              <EmptyDetail hasCases={!!cases.data?.cases.length} />
            )}
          </section>
        </div>
      )}

      {tab === "schedule" && (
        <Schedule data={schedule.data} error={schedule.error} onCase={openCase} />
      )}

      {tab === "activity" && (
        <section className="sheet">
          <h2 className="sheet__title">Everything that happened, newest first</h2>
          <ActivityFeed items={activity.data?.items ?? null} error={activity.error} onCase={openCase} />
        </section>
      )}
    </div>
  );
}

function EmptyDetail({ hasCases }: { hasCases: boolean }) {
  return (
    <div className="empty">
      <p className="empty__title">{hasCases ? "Pick a case to see its work order" : "No cases yet"}</p>
      <p className="empty__body">
        {hasCases
          ? "Every chat, email and form a customer sends, and every booking, change and cancellation, shows up on the work order."
          : "Book a visit in the chat or send the enquiry form on the Try it page. The case appears here within seconds."}
      </p>
    </div>
  );
}
