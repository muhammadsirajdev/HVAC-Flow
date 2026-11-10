import { useState, type FormEvent } from "react";
import { useAccess } from "../lib/access";
import { Icon } from "./Icon";

/** The office password form. `compact` sits inside the demo notice; otherwise it fills the page. */
export function SignIn({ compact = false, onDone }: { compact?: boolean; onDone?: () => void }) {
  const { signIn } = useAccess();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(password);
      setPassword("");
      onDone?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const form = (
    <form className="signin__form" onSubmit={submit}>
      <label className="signin__label" htmlFor="office-password">Office password</label>
      <div className="signin__row">
        <input
          id="office-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          placeholder={compact ? "Office password" : undefined}
        />
        <button className="btn btn--primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
    </form>
  );

  if (compact) return form;

  return (
    <section className="signin" aria-labelledby="signin-title">
      <span className="signin__icon" aria-hidden="true"><Icon name="lock" size={22} /></span>
      <h1 id="signin-title" className="signin__title">The office is for staff</h1>
      <p className="signin__body">
        It shows every customer's name, phone, address and messages. Sign in with the office password to open it.
      </p>
      {form}
    </section>
  );
}
