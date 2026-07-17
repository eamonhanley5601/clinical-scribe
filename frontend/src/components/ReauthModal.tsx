import { FormEvent, useState } from "react";
import { useAuth } from "../auth";
import { ApiError } from "../api";

/**
 * Shown when a background action (autosave, generate, save) hits a 401. The caller's form
 * state is untouched while this is open -- on successful re-login we just resolve, and the
 * caller re-issues the exact request that failed, so the provider's edits are never lost.
 */
export default function ReauthModal({ onResolved, onCancel }: { onResolved: () => void; onCancel: () => void }) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      onResolved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to log in");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <form className="card modal-card" onSubmit={handleSubmit}>
        <div className="warn-banner">
          Your session expired. Your unsaved note has <strong>not</strong> been lost — sign in again to continue.
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="field">
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus />
        </div>
        <div className="field">
          <label>Password</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" type="submit" disabled={loading} style={{ flex: 1 }}>
            {loading ? "Signing in..." : "Sign in and retry"}
          </button>
          <button type="button" className="ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
