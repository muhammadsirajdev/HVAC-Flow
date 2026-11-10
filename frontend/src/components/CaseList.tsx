import type { CaseRow, Status } from "../api";
import { ago, channelLabel, displayName, eventVerb, sentence, STATUS, STATUS_ORDER } from "../lib/format";
import { useNow } from "../lib/hooks";
import { channelIcon, Icon } from "./Icon";

interface Props {
  rows: CaseRow[] | null;
  error: string | null;
  counts?: Record<Status, number>;
  status: string;
  channel: string;
  query: string;
  selected: number | null;
  onQuery: (v: string) => void;
  onStatus: (s: string) => void;
  onChannel: (c: string) => void;
  onSelect: (id: number) => void;
}

export function CaseList(p: Props) {
  const now = useNow();
  const total = p.counts ? Object.values(p.counts).reduce((a, b) => a + b, 0) : null;

  return (
    <section className="desk__list" aria-label="Cases">
      <div className="filters">
        <label className="search">
          <Icon name="search" size={17} />
          <span className="sr-only">Search cases</span>
          <input
            type="search"
            value={p.query}
            placeholder="Name, email, phone or case number"
            onChange={(e) => p.onQuery(e.target.value)}
          />
        </label>

        <div className="chips" role="group" aria-label="Filter by status">
          <Chip active={!p.status} onClick={() => p.onStatus("")} label="All" count={total} />
          {STATUS_ORDER.map((s) => (
            <Chip key={s} status={s} active={p.status === s} onClick={() => p.onStatus(p.status === s ? "" : s)}
              label={STATUS[s].label} count={p.counts?.[s] ?? null} />
          ))}
        </div>

        <label className="select">
          <span className="select__label">Came in by</span>
          <select value={p.channel} onChange={(e) => p.onChannel(e.target.value)}>
            <option value="">Any channel</option>
            <option value="web">Website chat</option>
            <option value="form">Website form</option>
            <option value="email">Email</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
        </label>
      </div>

      {p.error && !p.rows ? (
        <p className="notice notice--error" role="alert">{p.error}</p>
      ) : !p.rows ? (
        <ul className="rows" aria-busy="true">
          {Array.from({ length: 6 }, (_, i) => <li key={i} className="row row--ghost" />)}
        </ul>
      ) : p.rows.length === 0 ? (
        <div className="empty empty--list">
          <p className="empty__title">No matching cases</p>
          <p className="empty__body">
            {p.status || p.channel || p.query ? "Clear a filter to see more." : "New cases appear here as customers get in touch."}
          </p>
        </div>
      ) : (
        <ul className="rows">
          {p.rows.map((r) => (
            <li key={r.case_id}>
              <button
                type="button"
                className={r.case_id === p.selected ? "row row--active" : "row"}
                aria-current={r.case_id === p.selected ? "true" : undefined}
                onClick={() => p.onSelect(r.case_id)}
              >
                <span className={`row__dot dot--${r.status}`} aria-hidden="true" />
                <span className="row__main">
                  <span className="row__name">{displayName(r.customer.name, r.customer.email)}</span>
                  <span className="row__what">{summary(r)}</span>
                </span>
                <span className="row__side">
                  <span className="row__num">{r.case_id}</span>
                  <span className="row__when">{ago(r.last_event?.at ?? r.updated_at, now)}</span>
                </span>
                <span className="row__meta">
                  <Icon name={channelIcon(r.channel)} size={14} />
                  {channelLabel(r.channel)}
                  <span className="row__status">{STATUS[r.status].label}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function summary(r: CaseRow): string {
  if (r.status === "booked" && r.visit?.active && r.visit.slot) return `${r.visit.service}, ${r.visit.slot}`;
  if (r.status === "cancelled" && r.visit?.slot) return `Cancelled ${r.visit.slot}`;
  if (r.last_event) {
    const v = eventVerb({ from_status: null, to_status: r.last_event.to_status, reason: r.last_event.reason, channel: r.channel });
    if (r.status === "needs_person" && r.last_event.reason) return sentence(r.last_event.reason);
    return sentence(v.verb);
  }
  return sentence(r.note ?? "");
}

function Chip({ label, count, active, onClick, status }: {
  label: string; count: number | null; active: boolean; onClick: () => void; status?: Status;
}) {
  return (
    <button type="button" className={active ? "chip chip--on" : "chip"} aria-pressed={active} onClick={onClick}>
      {status && <span className={`chip__dot dot--${status}`} aria-hidden="true" />}
      {label}
      {count !== null && <span className="chip__count">{count}</span>}
    </button>
  );
}
