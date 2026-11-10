import type { ReactNode } from "react";
import type { Overview } from "../api";
import { displayName, relativeDay, time } from "../lib/format";

interface Props {
  data: Overview | null;
  error: string | null;
  onNeedsPerson: () => void;
  onSchedule: () => void;
  onCase: (id: number) => void;
}

/** The office's glance: what needs a person, who is on the schedule, what came in. */
export function DispatchBoard({ data, error, onNeedsPerson, onSchedule, onCase }: Props) {
  const n = (v: number | undefined) => (data ? String(v ?? 0) : "–");
  const waiting = data?.by_status.needs_person ?? 0;
  const next = data?.next_visit;

  return (
    <section className="board" aria-label="Today at a glance">
      <div className="board__inner">
        <div className="board__intro">
          <h1 className="board__title">Office</h1>
          <p className="board__lede">
            Every customer who chatted, emailed or sent the form, and what happened next.
          </p>
        </div>

        {error && !data ? (
          <p className="board__error" role="alert">{error}</p>
        ) : (
          <div className="readings">
            <Reading label="Need a person" value={n(data?.by_status.needs_person)} alert={waiting > 0}
              onClick={onNeedsPerson} hint="Show cases waiting for the office" />
            <Reading label="Visits today" value={n(data?.visits_today)} onClick={onSchedule} hint="Open the schedule" />
            <Reading label="Tomorrow" value={n(data?.visits_tomorrow)} onClick={onSchedule} hint="Open the schedule" />
            <Reading label="New this week" value={n(data?.new_7d)} />
            <Reading
              wide
              label="Next visit"
              onClick={next ? () => onCase(next.case_id) : undefined}
              hint={next ? `Open case ${next.case_id}` : undefined}
              value={
                next ? (
                  <>
                    <span className="reading__when">{relativeDay(next.starts_at)}, {time(next.starts_at)}</span>
                    <span className="reading__who">{displayName(next.name)}, {next.service.toLowerCase()}</span>
                  </>
                ) : (
                  <span className="reading__who">{data ? `Nothing booked yet. ${data.open_slots} open slots.` : "–"}</span>
                )
              }
            />
          </div>
        )}
      </div>
    </section>
  );
}

function Reading({ label, value, onClick, hint, alert = false, wide = false }: {
  label: string; value: ReactNode; onClick?: () => void; hint?: string; alert?: boolean; wide?: boolean;
}) {
  const cls = ["reading", alert && "reading--alert", wide && "reading--wide"].filter(Boolean).join(" ");
  const body = (
    <>
      <span className="reading__label">{label}</span>
      <span className="reading__value">{value}</span>
    </>
  );
  return onClick ? (
    <button type="button" className={cls} onClick={onClick} title={hint}>{body}</button>
  ) : (
    <div className={cls}>{body}</div>
  );
}
