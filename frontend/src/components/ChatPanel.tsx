import { FormEvent, useEffect, useRef, useState } from "react";
import { useAccess } from "../lib/access";
import { Link } from "react-router-dom";
import { ChatReply, sendChat, sendChatFallback } from "../api";
import { newSessionId, store } from "../lib/hooks";
import { FanMark, Icon } from "./Icon";

interface Line {
  id: number;
  from: "you" | "desk";
  text: string;
  reply?: Pick<ChatReply, "intent" | "case_id" | "booked" | "emergency" | "trace">;
  error?: boolean;
}

const KEY = "mdcold.chat";
const STARTERS = [
  "My AC is running but blowing warm air",
  "I'd like to book a maintenance visit this week",
  "How much is a service call?",
  "Do you work in Hialeah?",
];

export function ChatPanel({ phone, onBooked }: { phone: string; onBooked?: (caseId: number) => void }) {
  const saved = store.get<{ session: string; lines: Line[] } | null>(KEY, null);
  const [session, setSession] = useState(saved?.session ?? newSessionId());
  const [lines, setLines] = useState<Line[]>(saved?.lines ?? []);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [fallback, setFallback] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => store.set(KEY, { session, lines }), [session, lines]);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [lines, busy, fallback]);

  const bookedCase = [...lines].reverse().find((l) => l.reply?.booked && l.reply.case_id)?.reply?.case_id ?? null;

  async function send(message: string) {
    const msg = message.trim();
    if (!msg || busy) return;
    setText("");
    setLines((l) => [...l, { id: Date.now(), from: "you", text: msg }]);
    setBusy(true);
    try {
      const r = await sendChat(session, msg);
      const wasBooked = bookedCase;
      setLines((l) => [...l, { id: Date.now() + 1, from: "desk", text: r.reply, reply: r }]);
      if (r.fallback_form) setFallback(true);
      if (r.booked && r.case_id && r.case_id !== wasBooked) onBooked?.(r.case_id);
    } catch (e) {
      setLines((l) => [...l, {
        id: Date.now() + 1, from: "desk", error: true,
        text: e instanceof Error ? e.message : "The message didn't go through. Try again.",
      }]);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  function restart() {
    setSession(newSessionId());
    setLines([]);
    setFallback(false);
    store.remove(KEY);
    input.current?.focus();
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };

  return (
    <section className="chat" aria-label="Website chat">
      <header className="chat__head">
        <FanMark size={34} spin={busy} />
        <div className="chat__who">
          <p className="chat__name">MD Cold front desk</p>
          <p className="chat__state" aria-live="polite">{busy ? "Writing a reply…" : "Answers right away, day and night"}</p>
        </div>
        <div className="chat__tools">
          <label className="toggle" title="Show which steps of the agent ran for each reply">
            <input type="checkbox" checked={showSteps} onChange={(e) => setShowSteps(e.target.checked)} />
            <span className="toggle__track" aria-hidden="true"><span className="toggle__knob" /></span>
            <span className="toggle__text">Agent steps</span>
          </label>
          {lines.length > 0 && (
            <button type="button" className="chat__restart" onClick={restart} title="Start a new conversation">
              <Icon name="refresh" size={16} /><span>New chat</span>
            </button>
          )}
        </div>
      </header>

      <div className="chat__scroll" ref={scroller} aria-live="polite" aria-relevant="additions">
        {lines.length === 0 ? (
          <div className="chat__hello">
            <p className="bubble bubble--desk">
              Hi, this is MD Cold Services. Tell me what your AC is doing, or ask about prices, areas and hours.
              I can book a technician for you right here.
            </p>
            <div className="starters" role="group" aria-label="Try one of these">
              {STARTERS.map((s) => (
                <button key={s} type="button" className="starter" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          lines.map((l) => (
            <div key={l.id} className={`line line--${l.from}`}>
              <p className={[
                "bubble", `bubble--${l.from}`,
                l.reply?.emergency && "bubble--emergency",
                l.error && "bubble--error",
              ].filter(Boolean).join(" ")}>
                {l.text}
              </p>
              {l.reply?.emergency && (
                <a className="callnow" href={`tel:${phone.replace(/[^\d+]/g, "")}`}>
                  <Icon name="phone" size={16} /> Call {phone} now
                </a>
              )}
              {showSteps && l.reply?.trace && (
                <p className="steps" aria-label="Agent steps">
                  {l.reply.intent && <span className="steps__intent">{l.reply.intent.replace(/_/g, " ")}</span>}
                  {l.reply.trace.map((t, i) => <span key={i} className="steps__node">{t}</span>)}
                </p>
              )}
              {l.reply?.booked && l.reply.case_id && <Ticket caseId={l.reply.case_id} />}
            </div>
          ))
        )}
        {busy && (
          <div className="line line--desk">
            <p className="bubble bubble--desk bubble--typing" aria-label="The front desk is typing">
              <span /><span /><span />
            </p>
          </div>
        )}
        {fallback && <FallbackForm session={session} phone={phone} onDone={(m) => {
          setFallback(false);
          setLines((l) => [...l, { id: Date.now(), from: "desk", text: m }]);
        }} />}
      </div>

      <form className="chat__compose" onSubmit={onSubmit}>
        <label className="sr-only" htmlFor="chat-input">Message</label>
        <textarea
          id="chat-input"
          ref={input}
          rows={1}
          value={text}
          maxLength={2000}
          placeholder="Type a message"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
        />
        <button type="submit" className="chat__send" disabled={busy || !text.trim()}>
          <Icon name="send" size={18} />
          <span className="sr-only">Send</span>
        </button>
      </form>
    </section>
  );
}

/** The work order that prints out of the chat when a visit is booked. */
function Ticket({ caseId }: { caseId: number }) {
  const { me } = useAccess();
  return (
    <div className="ticket" role="status">
      <div className="ticket__top">
        <span className="ticket__label">Visit booked</span>
        <span className="ticket__num">Case {caseId}</span>
      </div>
      <p className="ticket__body">
        {me?.demo_mode
          ? "In the live product a confirmation email goes out now. In this demo it's written but not sent. The case is already in the office view."
          : "The confirmation goes out by email and the office gets a Slack message. The case is already in the office view."}
      </p>
      <Link className="ticket__link" to={`/office?case=${caseId}`}>
        Open case {caseId} in the office
      </Link>
    </div>
  );
}

function FallbackForm({ session, phone, onDone }: { session: string; phone: string; onDone: (m: string) => void }) {
  const [f, setF] = useState({ name: "", phone: "", email: "", problem: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await sendChatFallback({ session_id: session, ...f });
      onDone(r.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't go through.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="fallback" onSubmit={submit}>
      <p className="fallback__lede">
        The assistant can't answer right now. Leave your details and the office will call you back, or call {phone}.
      </p>
      <div className="fallback__grid">
        <input required placeholder="Name" value={f.name} onChange={set("name")} aria-label="Name" />
        <input required placeholder="Phone" value={f.phone} onChange={set("phone")} aria-label="Phone" inputMode="tel" />
        <input required type="email" placeholder="Email" value={f.email} onChange={set("email")} aria-label="Email" />
        <input required placeholder="What's wrong?" value={f.problem} onChange={set("problem")} aria-label="Problem" />
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      <button className="btn btn--primary" disabled={busy}>{busy ? "Sending…" : "Ask for a call back"}</button>
    </form>
  );
}
