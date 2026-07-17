import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, DeactivatedError, SessionExpiredError, streamGenerateNote } from "../api";
import { Encounter, Icd10SearchResult } from "../types";
import Icd10Search from "../components/Icd10Search";
import VersionHistory from "../components/VersionHistory";
import ReauthModal from "../components/ReauthModal";
import DeactivatedNotice from "../components/DeactivatedNotice";
import VoiceRecorder, { appendTranscriptChunk } from "../components/VoiceRecorder";
import { NO_CLINICAL_CONTENT_MARKER, parsePartialSoap, SoapDraft } from "../soapParse";
import { useAuth } from "../auth";

type PendingRetry = (() => void) | null;
interface LocationState {
  autoGenerate?: boolean;
}

export default function EncounterEditor() {
  const { logout } = useAuth();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const autoGenerate = (location.state as LocationState | null)?.autoGenerate ?? false;

  const [loadingInitial, setLoadingInitial] = useState(true);
  const [deactivated, setDeactivated] = useState(false);
  const [encounter, setEncounter] = useState<Encounter | null>(null);

  const [transcript, setTranscript] = useState("");
  const [soap, setSoap] = useState<SoapDraft>({ subjective: "", objective: "", assessment: "", plan: "" });
  const [icd10Codes, setIcd10Codes] = useState<Icd10SearchResult[]>([]);

  const [generating, setGenerating] = useState(false);
  const [noClinicalContent, setNoClinicalContent] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showIcdPopover, setShowIcdPopover] = useState(false);
  const [pendingRetry, setPendingRetry] = useState<PendingRetry>(null);

  const autosaveTimer = useRef<ReturnType<typeof setTimeout>>();
  const hydrating = useRef(true);
  const autoGenerateFired = useRef(false);

  async function loadEncounter() {
    if (!id) return;
    try {
      const e = await api.get<Encounter>(`/encounters/${id}`);
      hydrating.current = true;
      setEncounter(e);
      setTranscript(e.transcript_text ?? "");
      setSoap({
        subjective: e.draft_subjective ?? "",
        objective: e.draft_objective ?? "",
        assessment: e.draft_assessment ?? "",
        plan: e.draft_plan ?? "",
      });
      // Server-resolved, lookup-table-verified attachment state -- persists across
      // reload/resume independent of whatever the Assessment prose says.
      setIcd10Codes((e.draft_icd10_codes ?? []).map((c) => ({ ...c, score: 1 })));
      setTimeout(() => {
        hydrating.current = false;
      }, 0);
      setLoadingInitial(false);
    } catch (err) {
      if (err instanceof DeactivatedError) {
        setDeactivated(true);
        setLoadingInitial(false);
      } else if (err instanceof SessionExpiredError) {
        // Stale token from a long-open tab -- retry the same load once re-authenticated
        // instead of showing "not found" or a blank error state.
        setPendingRetry(() => loadEncounter);
      } else {
        setLoadingInitial(false);
      }
    }
  }

  useEffect(() => {
    loadEncounter();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (autoGenerate && encounter && !autoGenerateFired.current) {
      autoGenerateFired.current = true;
      handleGenerate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [encounter]);

  // Autosave: debounced write-through so a refresh resumes from the DB, same pattern as before.
  useEffect(() => {
    if (!encounter || hydrating.current) return;
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(() => {
      api
        .patch(`/encounters/${encounter.id}/draft`, {
          transcript_text: transcript,
          draft_subjective: soap.subjective,
          draft_objective: soap.objective,
          draft_assessment: soap.assessment,
          draft_plan: soap.plan,
          icd10_codes: icd10Codes.map((c) => ({ code: c.code, description: c.description })),
        })
        .catch(() => {
          /* best-effort; next autosave tick will retry */
        });
    }, 1200);
    return () => clearTimeout(autosaveTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transcript, soap, icd10Codes]);

  async function handleGenerate() {
    if (!encounter || !transcript.trim()) return;
    setGenerating(true);
    setGenError(null);
    setNoClinicalContent(null);
    // Clear any existing note (first-time or a prior saved/generated one on regenerate) so the
    // skeleton loader shows immediately and the new note fills in progressively from a clean
    // slate, rather than old text lingering and getting overwritten piecemeal mid-stream.
    setSoap({ subjective: "", objective: "", assessment: "", plan: "" });
    setIcd10Codes([]);
    let accumulated = "";
    try {
      await streamGenerateNote(encounter.id, transcript, {
        onDelta: (chunk) => {
          accumulated += chunk;
          setSoap(parsePartialSoap(accumulated));
        },
        onDone: (finalSections, codes) => {
          setSoap(finalSections);
          setIcd10Codes(codes.map((c) => ({ ...c, score: 1 })));
          setGenerating(false);
        },
        onNoClinicalContent: (raw) => {
          setNoClinicalContent(
            raw.replace(NO_CLINICAL_CONTENT_MARKER, "").trim() ||
              "The transcript didn't contain clinically meaningful content, so no note was generated.",
          );
          setGenerating(false);
        },
        onGenerationError: (message) => {
          setGenError(message);
          setGenerating(false);
        },
      });
    } catch (err) {
      setGenerating(false);
      if (err instanceof SessionExpiredError) {
        setPendingRetry(() => handleGenerate);
      } else if (err instanceof DeactivatedError) {
        setDeactivated(true);
      } else {
        setGenError(err instanceof ApiError ? err.message : "Failed to generate note");
      }
    }
  }

  // Strips the line(s) mentioning this code out of the Assessment text -- covers both a
  // manually-added code (always its own "CODE - Description" line, see handleSelectIcd10) and
  // an AI-written code (observed in practice to also land on its own line/clause). Only drops
  // whole lines that mention the code, so surrounding prose in other lines is untouched.
  function removeIcd10CodeFromAssessment(text: string, code: string): string {
    return text
      .split("\n")
      .filter((line) => !line.toUpperCase().includes(code.toUpperCase()))
      .join("\n");
  }

  function handleRemoveIcd10(code: string) {
    setIcd10Codes((prev) => prev.filter((x) => x.code !== code));
    setSoap((prev) => ({ ...prev, assessment: removeIcd10CodeFromAssessment(prev.assessment, code) }));
  }

  function handleSelectIcd10(result: Icd10SearchResult) {
    setIcd10Codes((prev) => (prev.some((c) => c.code === result.code) ? prev : [...prev, result]));
    setSoap((prev) => ({
      ...prev,
      assessment: prev.assessment ? `${prev.assessment}\n${result.code} - ${result.description}` : `${result.code} - ${result.description}`,
    }));
  }

  async function handleSave() {
    if (!encounter) return;
    setSaving(true);
    try {
      const version = await api.post<{ version_number: number }>(`/encounters/${encounter.id}/save`, {
        ...soap,
        icd10_codes: icd10Codes.map((c) => ({ code: c.code, description: c.description })),
      });
      navigate("/", { state: { flash: `Saved as version ${version.version_number}.` } });
    } catch (err) {
      if (err instanceof SessionExpiredError) {
        setPendingRetry(() => handleSave);
      } else if (err instanceof DeactivatedError) {
        setDeactivated(true);
      }
    } finally {
      setSaving(false);
    }
  }

  if (deactivated) return <DeactivatedNotice onSignOut={logout} />;
  if (pendingRetry && !encounter) {
    return (
      <div className="page muted">
        Loading encounter...
        <ReauthModal
          onCancel={() => setPendingRetry(null)}
          onResolved={() => {
            const retry = pendingRetry;
            setPendingRetry(null);
            retry?.();
          }}
        />
      </div>
    );
  }
  if (loadingInitial) return <div className="page muted">Loading encounter...</div>;
  if (!encounter) return <div className="page muted">Encounter not found.</div>;

  return (
    <div className="page">
      <button className="ghost" onClick={() => navigate("/")} style={{ padding: "4px 0", marginBottom: 12 }}>
        ← Back to encounters
      </button>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>
            {encounter.patient.first_name} {encounter.patient.last_name}
          </h1>
          <span className="muted">DOB {encounter.patient.date_of_birth}</span>
          {encounter.is_returning_patient ? (
            <span className="pill returning">Returning patient</span>
          ) : (
            <span className="pill new">New patient</span>
          )}
        </div>
        <button className="ghost" onClick={() => setShowHistory((s) => !s)} disabled={encounter.latest_version === 0}>
          {showHistory ? "Hide" : "View"} version history ({encounter.latest_version})
        </button>
      </div>

      {noClinicalContent && (
        <div className="warn-banner">
          <strong>No note generated.</strong> {noClinicalContent}
        </div>
      )}
      {genError && <div className="error-banner">{genError}</div>}

      {showHistory ? (
        <div className="card">
          <VersionHistory encounterId={encounter.id} />
        </div>
      ) : (
        <div className="workspace-grid">
          <div className="card">
            <div className="card-header">
              <span className="card-title">Encounter transcript</span>
              <VoiceRecorder
                disabled={generating}
                onTranscript={(text) => setTranscript((prev) => appendTranscriptChunk(prev, text))}
              />
            </div>
            <textarea
              style={{ minHeight: 320 }}
              placeholder="Paste the raw encounter transcript, or type freeform clinical observations..."
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
            />
            <button
              className="primary"
              style={{ width: "100%", marginTop: 10 }}
              disabled={generating || !transcript.trim()}
              onClick={handleGenerate}
            >
              {generating ? (
                <>
                  Generating <span className="spinner" />
                </>
              ) : encounter.latest_version > 0 || soap.subjective ? (
                "Regenerate note"
              ) : (
                "Generate note"
              )}
            </button>
            {generating && (
              <p className="muted" style={{ marginTop: 6, marginBottom: 0 }}>
                Checking patient history, then streaming the note in (~20-30s).
              </p>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <span className="card-title">SOAP note</span>
            </div>
            {(["subjective", "objective", "assessment", "plan"] as const).map((key) => (
              <div className="soap-section" key={key}>
                <h4>{key}</h4>
                <textarea value={soap[key]} onChange={(e) => setSoap((prev) => ({ ...prev, [key]: e.target.value }))} />
                {key === "assessment" && icd10Codes.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    {icd10Codes.map((c) => (
                      <span className="icd10-chip" key={c.code}>
                        {c.code}
                        <button onClick={() => handleRemoveIcd10(c.code)}>×</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            <button
              className="primary"
              style={{ width: "100%" }}
              disabled={saving || generating || !soap.subjective}
              onClick={handleSave}
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      )}

      {!showHistory && !generating && (
        <>
          <button
            className="primary"
            onClick={() => setShowIcdPopover((s) => !s)}
            style={{
              position: "fixed",
              bottom: 24,
              right: 24,
              borderRadius: 999,
              padding: "10px 18px",
              boxShadow: "0 4px 14px rgba(20, 30, 45, 0.25)",
              zIndex: 30,
            }}
          >
            {showIcdPopover ? "Close" : "+ ICD-10 code"}
          </button>
          {showIcdPopover && (
            <div
              className="card"
              style={{ position: "fixed", bottom: 72, right: 24, width: 340, zIndex: 30 }}
            >
              <div className="card-header">
                <span className="card-title">Add ICD-10 code</span>
              </div>
              <Icd10Search
                onSelect={(r) => {
                  handleSelectIcd10(r);
                }}
              />
              <p className="muted" style={{ marginTop: 8, marginBottom: 0 }}>
                Selected codes append to the Assessment section.
              </p>
            </div>
          )}
        </>
      )}

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
