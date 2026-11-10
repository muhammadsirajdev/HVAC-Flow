import { useState } from "react";
import type { Booking, CaseDetail } from "../api";
import { getCase } from "../api";
import {
  ago, buildJourney, channelLabel, dateTime, dayLong, displayName, initials, JourneyItem, phone, STATUS, time,
} from "../lib/format";
import { useNow, usePoll } from "../lib/hooks";
import { channelIcon, Icon } from "./Icon";
import { ChannelTag, StatusTag } from "./Tags";

interface Props {
  caseId: number;
  onClose: () => void;
  onCase: (id: number) => void;
}

export function WorkOrder({ caseId, onClose, onCase }: Props) {
  const { data, error } = usePoll(() => getCase(caseId), 8000, [caseId]);
  const d = data && data.case.case_id === caseId ? data : null;

  return (
    <article className="order" aria-labelledby="order-title">
      <button type="button" className="order__back" onClick={onClose}>
        <Icon name="back" size={16} /> All cases
      </button>
      {error && !d ? (
        <p className="notice notice--error" role="alert">{error}</p>
      ) : !d ? (
        <div className="order__paper order__paper--loading" aria-busy="true">
          <p className="order__loading">Pulling case {caseId}…</p>
        </div>
      ) : (
        <Paper d={d} onCase={onCase} />
      )}
    </article>
  );
}

function Paper({ d, onCase }: { d: CaseDetail; onCase: (id: number) => void }) {
  const now = useNow();
  const c = d.case;
  const active = d.bookings.find((b) => b.active) ?? null;
  const past = d.bookings.filter((b) => !b.active).reverse();
  const name = displayName(d.customer.name, d.customer.email);

  return (
    <div className="order__paper">
      <header className="order__head">
        <div className="order__number">
          <span className="order__case">Case</span>
          <span id="order-title" className="order__digits">{c.case_id}</span>
        </div>
        <div className="order__state">
          <StatusTag status={c.status} />
          <p className="order__opened">
            Came in by <ChannelTag channel={c.channel} quiet /> {ago(c.created_at, now)}
          </p>
        </div>
      </header>

      {c.status === "needs_person" && (
        <p className="callout callout--needs">
          <Icon name="alert" size={18} />
          <span>
            <strong>The AI has stepped back on this case.</strong> Someone from the office replies to {name.split(" ")[0]}
            {d.customer.phone ? ` at ${phone(d.customer.phone)}` :d.customer.email ? ` at ${d.customer.email}` : ""}.
            {c.note && <span className="callout__note"> {c.note}</span>}
          </span>
        </p>
      )}

      <div className="order__grid">
        <section className="field-block" aria-label="Customer">
          <h3 className="field-block__title">Customer</h3>
          <div className="person">
            <span className="person__mark" aria-hidden="true">{initials(d.customer.name, d.customer.email)}</span>
            <div>
              <p className="person__name">{name}</p>
              <p className="person__since">Customer since {dayLong(d.customer.since)}</p>
            </div>
          </div>
          <ul className="facts">
            {d.customer.phone && (
              <li><Icon name="phone" size={16} />
                {hidden(d.customer.phone) ? <span>{d.customer.phone}</span>
                  : <a href={`tel:${d.customer.phone}`}>{phone(d.customer.phone)}</a>}
              </li>
            )}
            {d.customer.email && (
              <li><Icon name="mail" size={16} />
                {hidden(d.customer.email) ? <span>{d.customer.email}</span>
                  : <a href={`mailto:${d.customer.email}`}>{d.customer.email}</a>}
              </li>
            )}
            {(d.customer.address || active?.address) && (
              <li><Icon name="pin" size={16} /><span>{d.customer.address || active?.address}</span></li>
            )}
          </ul>
          {d.other_cases.length > 0 && (
            <div className="history">
              <p className="history__title">Earlier cases</p>
              <ul className="history__list">
                {d.other_cases.map((o) => (
                  <li key={o.case_id}>
                    <button type="button" className="link" onClick={() => onCase(o.case_id)}>
                      Case {o.case_id}
                    </button>
                    <span className="history__meta">{STATUS[o.status].label}, {dayLong(o.created_at)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="field-block field-block--visit" aria-label="Visit">
          <h3 className="field-block__title">Visit</h3>
          {active ? <VisitCard b={active} /> : (
            <p className="visit__none">
              {c.status === "cancelled" ? "The visit was cancelled. The slot is open again." :
                c.status === "done" || c.status === "closed" ? "The job is finished." :
                "Nothing booked yet."}
            </p>
          )}
          {past.length > 0 && (
            <ul className="visit__past">
              {past.map((b) => (
                <li key={b.booking_id}>
                  <s>{b.slot}</s> <span>{b.service}, called off</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <Journey d={d} />
    </div>
  );
}

function VisitCard({ b }: { b: Booking }) {
  const steps = [
    { done: !!b.confirmation_sent_at, label: "Confirmation emailed", at: b.confirmation_sent_at },
    { done: !!b.slack_posted_at, label: "Office told in Slack", at: b.slack_posted_at },
    { done: b.reminded, label: b.reminded ? "Reminder sent" : "Reminder goes out the evening before", at: null },
  ];
  return (
    <div className="visit">
      <p className="visit__day">{dayLong(b.starts_at)}</p>
      <p className="visit__time">
        {time(b.starts_at)}<span className="visit__to"> to {time(b.ends_at)}</span>
      </p>
      <p className="visit__service"><Icon name="wrench" size={16} /> {b.service}</p>
      {b.problem && <p className="visit__problem">“{b.problem}”</p>}
      <p className="visit__addr"><Icon name="pin" size={16} /> {b.address}</p>
      {b.technician && <p className="visit__tech"><Icon name="user" size={16} /> {b.technician}</p>}
      <ul className="checks">
        {steps.map((s) => (
          <li key={s.label} className={s.done ? "checks__item checks__item--done" : "checks__item"}>
            <Icon name={s.done ? "check" : "clock"} size={15} />
            {s.label}
            {s.at && <span className="checks__at">{time(s.at)}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- the journey: one line through everything that happened ----------
function Journey({ d }: { d: CaseDetail }) {
  const { items, toneAt } = buildJourney(d);
  if (!items.length) return null;
  return (
    <section className="journey" aria-label="What happened">
      <h3 className="journey__title">What happened</h3>
      <ol className="journey__list">
        {items.map((it, i) => (
          <li key={it.key} className={`step step--${it.kind} tone--${toneAt[i]}`}>
            <span className="step__rail" aria-hidden="true">
              <span className="step__node" />
            </span>
            <div className="step__body">
              <Step it={it} name={displayName(d.customer.name, d.customer.email).split(" ")[0]} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Step({ it, name }: { it: JourneyItem; name: string }) {
  if (it.kind === "status") {
    return (
      <>
        <p className="step__line">
          <span className="step__text">
            <span className="step__who">{name}</span> {it.verb}
            {it.slot && it.to === "booked" && <> for <strong>{it.slot}</strong></>}
          </span>
          <time className="step__at" dateTime={it.at}>{dateTime(it.at)}</time>
        </p>
        {it.reason && <p className="step__reason">{it.reason}</p>}
      </>
    );
  }
  if (it.kind === "notice") {
    return (
      <p className="step__line step__line--notice">
        <span className="step__text step__text--notice"><Icon name={it.icon} size={15} /> {it.text}</span>
        <time className="step__at" dateTime={it.at}>{time(it.at)}</time>
      </p>
    );
  }
  return <MessageStep it={it} name={name} />;
}

function MessageStep({ it, name }: { it: Extract<JourneyItem, { kind: "message" }>; name: string }) {
  const [open, setOpen] = useState(false);
  const long = it.body.length > 360;
  const who = it.direction === "in" ? name : it.channel === "web" ? "AI desk" : "AI desk by email";
  const subject = typeof it.meta.subject === "string" ? it.meta.subject : null;
  return (
    <div className={`msg msg--${it.direction} msg--${it.channel}`}>
      <p className="msg__head">
        <Icon name={channelIcon(it.channel)} size={14} />
        <span className="msg__who">{who}</span>
        <span className="msg__via">{it.direction === "in" ? channelLabel(it.channel).toLowerCase() : ""}</span>
        <time className="step__at" dateTime={it.at}>{time(it.at)}</time>
      </p>
      {subject && it.direction === "in" && <p className="msg__subject">{subject}</p>}
      <p className={long && !open ? "msg__body msg__body--clip" : "msg__body"}>{it.body}</p>
      {long && (
        <button type="button" className="link link--small" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Show less" : "Show the whole message"}
        </button>
      )}
    </div>
  );
}

/** The public demo partly hides contact details ("•••"): those are shown as text, not call/email links. */
const hidden = (value: string) => value.includes("•");
