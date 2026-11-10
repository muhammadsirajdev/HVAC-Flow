import type { ScheduleSlot } from "../api";
import { dayDate, dayKey, displayName, relativeDay, time, weekday } from "../lib/format";

const dayName = (iso: string) => {
  const r = relativeDay(iso);
  return r === "Today" || r === "Tomorrow" ? r : weekday(iso);
};

interface Props {
  data: { tz: string; slots: ScheduleSlot[] } | null;
  error: string | null;
  onCase: (id: number) => void;
}

export function Schedule({ data, error, onCase }: Props) {
  if (error && !data) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!data) return <div className="sheet sheet--loading" aria-busy="true">Loading the week…</div>;

  const days = new Map<string, ScheduleSlot[]>();
  for (const s of data.slots) {
    const k = dayKey(s.starts_at);
    days.set(k, [...(days.get(k) ?? []), s]);
  }
  const booked = data.slots.filter((s) => s.case_id).length;
  const open = data.slots.filter((s) => !s.taken && !s.past).length;

  return (
    <section className="sheet" aria-label="Schedule">
      <div className="sheet__head">
        <h2 className="sheet__title">The next seven days</h2>
        <p className="sheet__sub">
          {booked} {booked === 1 ? "visit" : "visits"} booked, {open} open {open === 1 ? "slot" : "slots"} the AI can offer.
          Times are Miami time.
        </p>
      </div>
      {days.size === 0 ? (
        <div className="empty">
          <p className="empty__title">No slots this week</p>
          <p className="empty__body">Run <code>uv run python scripts/seed_demo_client.py</code> in backend/ to add 14 days of slots.</p>
        </div>
      ) : (
        <div className="week">
          {[...days.entries()].map(([k, slots]) => (
            <div className="day" key={k}>
              <h3 className="day__name">
                {dayName(slots[0].starts_at)}
                <span className="day__count">
                  {dayDate(slots[0].starts_at)}, {slots.filter((s) => s.case_id).length} booked
                </span>
              </h3>
              <ul className="day__slots">
                {slots.map((s) => (
                  <li key={s.slot_id}>
                    {s.case_id ? (
                      <button type="button" className={`slot slot--booked${s.past ? " slot--past" : ""}`}
                        onClick={() => onCase(s.case_id!)}>
                        <span className="slot__time">{time(s.starts_at)}</span>
                        <span className="slot__who">{displayName(s.name)}</span>
                        <span className="slot__what">{s.service}, case {s.case_id}</span>
                      </button>
                    ) : (
                      <span className={`slot ${s.past ? "slot--past" : s.taken ? "slot--held" : "slot--open"}`}>
                        <span className="slot__time">{time(s.starts_at)}</span>
                        <span className="slot__what">{s.past ? "Passed" : s.taken ? "Held" : "Open"}</span>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
