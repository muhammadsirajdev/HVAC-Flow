import { FormEvent, useEffect, useState } from "react";
import { useAccess } from "../lib/access";
import { Link } from "react-router-dom";
import { EnquiryResult, sendEnquiry } from "../api";
import { store } from "../lib/hooks";
import { Icon } from "./Icon";

const KEY = "mdcold.form";
const EMPTY = { name: "", email: "", phone: "", message: "" };

export function EnquiryForm({ inbox, onSent }: { inbox?: string; onSent?: (caseId: number | null) => void }) {
  const { me } = useAccess();
  const [f, setF] = useState(() => store.get(KEY, EMPTY));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EnquiryResult | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => store.set(KEY, { ...f, message: result ? "" : f.message }), [f, result]);
  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [busy]);

  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await sendEnquiry(f);
      setResult(r);
      onSent?.(r.case_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The form didn't go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <section className="enquiry enquiry--done" aria-label="Enquiry sent">
        <p className={result.sent ? "enquiry__result" : "enquiry__result enquiry__result--held"} role="status">
          <Icon name={result.sent ? "check" : "user"} size={18} />
          {result.message}
        </p>
        {result.body && (
          <div className="letter">
            <p className="letter__meta"><span>To</span> {result.to}</p>
            {result.subject && <p className="letter__meta"><span>Subject</span> {result.subject}</p>}
            <pre className="letter__body">{result.body}</pre>
          </div>
        )}
        <p className="enquiry__next">
          {result.preview
            ? "In the live product this lands in the customer's inbox, and replying to it gets another answer in the same thread."
            : <>
                {result.sent && "Check your inbox, and the spam folder if it's not there. "}
                Reply to that email and the AI answers again in the same thread.
              </>}
        </p>
        <div className="enquiry__actions">
          {result.case_id && (
            <Link className="btn btn--primary" to={`/office?case=${result.case_id}`}>Open case {result.case_id} in the office</Link>
          )}
          <button type="button" className="btn btn--quiet" onClick={() => { setResult(null); setF({ ...f, message: "" }); }}>
            Write another
          </button>
        </div>
      </section>
    );
  }

  return (
    <form className="enquiry" onSubmit={submit} aria-label="Enquiry form">
      <div className="enquiry__intro">
        <h2 className="enquiry__title">Or write to us</h2>
        <p className="enquiry__lede">
          This is the contact form a website would have. The email agent reads it, opens a case, and emails the answer
          to the address you give. It can book a visit too.
        </p>
      </div>

      <div className="field">
        <label htmlFor="eq-name">Your name</label>
        <input id="eq-name" required autoComplete="name" value={f.name} onChange={set("name")} maxLength={200} />
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor="eq-email">Email for the answer</label>
          <input id="eq-email" required type="email" autoComplete="email" value={f.email} onChange={set("email")} />
        </div>
        <div className="field">
          <label htmlFor="eq-phone">Phone <span className="field__opt">optional</span></label>
          <input id="eq-phone" type="tel" autoComplete="tel" inputMode="tel" value={f.phone} onChange={set("phone")} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="eq-msg">How can we help?</label>
        <textarea id="eq-msg" required rows={5} maxLength={4000} value={f.message} onChange={set("message")}
          placeholder="My upstairs unit is leaking water onto the ceiling. Can someone come Thursday morning?" />
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}

      <div className="enquiry__send">
        <button className="btn btn--primary" disabled={busy}>
          {busy ? "Sending…" : "Send enquiry"}
        </button>
        <p className="enquiry__fine" aria-live="polite">
          {busy
            ? `The agent is reading it and writing the answer. This usually takes 10 to 30 seconds (${elapsed} s).`
            : me?.demo_mode
              ? "This is a demo: the AI writes the email and shows it here instead of sending it."
              : `A real email is sent to the address above${inbox ? `, from ${inbox}` : ""}.`}
        </p>
      </div>
    </form>
  );
}
