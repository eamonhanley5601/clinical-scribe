/**
 * Shown whenever a page's data fetch throws DeactivatedError -- reused across Dashboard,
 * NewEncounter, and EncounterEditor so the "admin deactivates provider mid-session" non-happy
 * path renders identically regardless of which screen the provider was on when it happened.
 */
export default function DeactivatedNotice({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className="page" style={{ maxWidth: 480 }}>
      <div className="card">
        <div className="error-banner">
          Your account has been deactivated by an administrator. Any in-progress draft was not
          deleted — it will be exactly as you left it if your account is reactivated.
        </div>
        <button className="primary" style={{ width: "100%" }} onClick={onSignOut}>
          Return to sign in
        </button>
      </div>
    </div>
  );
}
