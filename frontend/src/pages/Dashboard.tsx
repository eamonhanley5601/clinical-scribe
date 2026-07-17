import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, DeactivatedError, SessionExpiredError } from "../api";
import { Encounter } from "../types";
import DeactivatedNotice from "../components/DeactivatedNotice";
import ReauthModal from "../components/ReauthModal";
import { useAuth } from "../auth";

interface LocationState {
  flash?: string;
}

export default function Dashboard() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const flash = (location.state as LocationState | null)?.flash;

  const [loading, setLoading] = useState(true);
  const [deactivated, setDeactivated] = useState(false);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [pendingRetry, setPendingRetry] = useState<(() => void) | null>(null);

  async function loadDashboard() {
    try {
      // /encounters/mine already returns every encounter regardless of status, sorted by most
      // recently updated -- that's also what makes it the single place multiple in-progress
      // drafts surface and stay resumable, without a separate "current draft" special case.
      const mine = await api.get<Encounter[]>("/encounters/mine");
      setEncounters(mine);
      setLoading(false);
    } catch (err) {
      if (err instanceof DeactivatedError) {
        setDeactivated(true);
        setLoading(false);
      } else if (err instanceof SessionExpiredError) {
        setPendingRetry(() => loadDashboard);
      } else {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    loadDashboard();
    if (flash) window.history.replaceState({}, "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (deactivated) return <DeactivatedNotice onSignOut={logout} />;
  if (loading && !pendingRetry) return <div className="page muted">Loading dashboard...</div>;

  const draftCount = encounters.filter((e) => e.status === "draft").length;

  return (
    <div className="page">
      {flash && <div className="ok-banner">{flash}</div>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Encounters</h1>
        <button className="primary" onClick={() => navigate("/encounters/new")}>
          + New encounter
        </button>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">
            All encounters{draftCount > 0 && <span className="muted"> · {draftCount} in progress</span>}
          </span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Category</th>
              <th>Status</th>
              <th>Versions</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {encounters.map((e) => (
              <tr key={e.id} className="clickable-row" onClick={() => navigate(`/encounters/${e.id}`)}>
                <td>
                  {e.patient.first_name} {e.patient.last_name}
                </td>
                <td className="muted">{e.template_name ?? "General"}</td>
                <td>
                  <span className={`pill ${e.status === "draft" ? "draft" : "saved"}`}>
                    {e.status === "draft" ? "In progress" : "Saved"}
                  </span>
                </td>
                <td>{e.latest_version}</td>
                <td>{new Date(e.updated_at).toLocaleString()}</td>
              </tr>
            ))}
            {encounters.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No encounters yet — start your first one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pendingRetry && (
        <ReauthModal
          onCancel={() => setPendingRetry(null)}
          onResolved={() => {
            const retry = pendingRetry;
            setPendingRetry(null);
            retry?.();
          }}
        />
      )}
    </div>
  );
}
