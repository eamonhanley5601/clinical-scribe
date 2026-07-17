import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, DeactivatedError, SessionExpiredError } from "../api";
import { Encounter, Template } from "../types";
import ReauthModal from "../components/ReauthModal";
import DeactivatedNotice from "../components/DeactivatedNotice";
import VoiceRecorder, { appendTranscriptChunk } from "../components/VoiceRecorder";
import { useAuth } from "../auth";

export default function NewEncounter() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [deactivated, setDeactivated] = useState(false);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [dob, setDob] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [transcript, setTranscript] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<(() => void) | null>(null);

  async function loadTemplates() {
    try {
      setTemplates(await api.get<Template[]>("/templates"));
      setLoading(false);
    } catch (err) {
      if (err instanceof DeactivatedError) {
        setDeactivated(true);
        setLoading(false);
      } else if (err instanceof SessionExpiredError) {
        // Don't flip to an error state here -- an hour-old token from a session that's been
        // open a while is routine, not exceptional. Keep showing "Loading..." underneath the
        // modal and retry the same fetch once re-authenticated.
        setPendingRetry(() => loadTemplates);
      } else {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleGenerate() {
    setSubmitting(true);
    setError(null);
    try {
      const encounter = await api.post<Encounter>("/encounters", {
        patient: { first_name: firstName, last_name: lastName, date_of_birth: dob },
        template_id: templateId || null,
      });
      await api.patch(`/encounters/${encounter.id}/draft`, { transcript_text: transcript });
      navigate(`/encounters/${encounter.id}`, { state: { autoGenerate: true } });
    } catch (err) {
      setSubmitting(false);
      if (err instanceof SessionExpiredError) {
        setPendingRetry(() => handleGenerate);
      } else if (err instanceof DeactivatedError) {
        setDeactivated(true);
      } else {
        setError("Failed to start encounter. Please try again.");
      }
    }
  }

  if (deactivated) return <DeactivatedNotice onSignOut={logout} />;
  if (loading && !pendingRetry) return <div className="page muted">Loading...</div>;

  const canSubmit = firstName && lastName && dob && transcript.trim() && !submitting;

  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <button className="ghost" onClick={() => navigate("/")} style={{ padding: "4px 0", marginBottom: 12 }}>
        ← Back to encounters
      </button>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 20px" }}>New encounter</h1>
      <div className="card">
        {error && <div className="error-banner">{error}</div>}
        <div style={{ display: "flex", gap: 10 }}>
          <div className="field" style={{ flex: 1 }}>
            <label>Patient first name</label>
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>Patient last name</label>
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <div className="field" style={{ flex: 1 }}>
            <label>Date of birth</label>
            <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>Encounter template</label>
            <select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">General / no template</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <label style={{ marginBottom: 0 }}>Encounter transcript</label>
            <VoiceRecorder onTranscript={(text) => setTranscript((prev) => appendTranscriptChunk(prev, text))} />
          </div>
          <textarea
            style={{ minHeight: 220 }}
            placeholder="Paste the raw encounter transcript, or type freeform clinical observations..."
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
          />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" style={{ flex: 1 }} disabled={!canSubmit} onClick={handleGenerate}>
            {submitting ? "Starting..." : "Generate note"}
          </button>
          <button className="ghost" onClick={() => navigate("/")}>
            Cancel
          </button>
        </div>
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
