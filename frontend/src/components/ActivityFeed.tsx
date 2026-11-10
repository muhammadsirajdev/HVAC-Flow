import type { ActivityItem } from "../api";
import { activitySentence, ago, dayKey, displayName, relativeDay, time } from "../lib/format";
import { useNow } from "../lib/hooks";
import { channelIcon, Icon } from "./Icon";

interface Props {
  items: ActivityItem[] | null;
  error: string | null;
  onCase: (id: number) => void;
  compact?: boolean;
  fresh?: Set<string>;
}

export function ActivityFeed({ items, error, onCase, compact = false, fresh }: Props) {
  const now = useNow(15000);
  if (error && !items) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!items) return <p className="feed__loading" aria-busy="true">Loading activity…</p>;
  if (!items.length)
    return (
      <div className="empty empty--feed">
        <p className="empty__title">Quiet so far</p>
        <p className="empty__body">Bookings, emails, changes and cancellations show up here as they happen.</p>
      </div>
    );

  let lastDay = "";
  return (
    <ol className={compact ? "feed feed--compact" : "feed"}>
      {items.map((i) => {
        const s = activitySentence(i);
        const day = dayKey(i.at);
        const header = !compact && day !== lastDay ? relativeDay(i.at) : null;
        lastDay = day;
        return (
          <li key={i.id} className={fresh?.has(i.id) ? "feed__item feed__item--fresh" : "feed__item"}>
            {header && <p className="feed__day">{header}</p>}
            <div className={`entry tone--${s.tone}`}>
              <span className="entry__icon" aria-hidden="true">
                <Icon name={i.kind === "email" ? (i.direction === "in" ? channelIcon(i.channel) : "send") : i.to_status === "open" && !i.from_status ? channelIcon(i.channel) : iconFor(i.to_status)} size={15} />
              </span>
              <p className="entry__text">
                <strong>{displayName(i.name, i.email)}</strong> {s.verb}
                {s.extra && <span className="entry__extra"> {i.kind === "email" ? `“${trim(s.extra)}”` : s.extra}</span>}
              </p>
              <span className="entry__side">
                <button type="button" className="link link--small" onClick={() => onCase(i.case_id)}>
                  Case {i.case_id}
                </button>
                <time dateTime={i.at} title={time(i.at)}>{compact ? ago(i.at, now) : time(i.at)}</time>
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const trim = (s: string) => (s.length > 110 ? `${s.slice(0, 110).trim()}…` : s);

function iconFor(status: string) {
  return { open: "chat", booked: "calendar", needs_person: "user", cancelled: "x", done: "wrench", closed: "check" }[status] ?? "bell";
}
