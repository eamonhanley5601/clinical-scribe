import { useEffect, useState } from "react";
import { api } from "../api";
import { NoteVersion } from "../types";
import { wordDiff } from "../diff";

const SECTIONS: (keyof Pick<NoteVersion, "subjective" | "objective" | "assessment" | "plan">)[] = [
  "subjective",
  "objective",
  "assessment",
  "plan",
];

export default function VersionHistory({ encounterId }: { encounterId: string }) {
  const [versions, setVersions] = useState<NoteVersion[]>([]);
  const [compareA, setCompareA] = useState<string | null>(null);
  const [compareB, setCompareB] = useState<string | null>(null);

  useEffect(() => {
    api.get<NoteVersion[]>(`/encounters/${encounterId}/versions`).then((v) => {
      setVersions(v);
      if (v.length >= 2) {
        setCompareB(v[0].id);
        setCompareA(v[1].id);
      } else if (v.length === 1) {
        setCompareB(v[0].id);
      }
    });
  }, [encounterId]);

  if (versions.length === 0) return <p className="muted">No saved versions yet.</p>;

  const a = versions.find((v) => v.id === compareA);
  const b = versions.find((v) => v.id === compareB);

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        <div style={{ flex: 1 }}>
          <label>Compare from (older)</label>
          <select value={compareA ?? ""} onChange={(e) => setCompareA(e.target.value || null)}>
            <option value="">(none)</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.version_number} - {new Date(v.saved_at).toLocaleString()} - {v.saved_by_name}
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label>Compare to (newer)</label>
          <select value={compareB ?? ""} onChange={(e) => setCompareB(e.target.value || null)}>
            <option value="">(none)</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.version_number} - {new Date(v.saved_at).toLocaleString()} - {v.saved_by_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {a && b && a.id !== b.id ? (
        <div>
          {SECTIONS.map((section) => {
            const tokens = wordDiff(a[section], b[section]);
            const changed = tokens.some((t) => t.type !== "same");
            return (
              <div className="soap-section" key={section}>
                <h4>{section}</h4>
                {!changed ? (
                  <p className="muted">No change.</p>
                ) : (
                  <p style={{ lineHeight: 1.7 }}>
                    {tokens.map((t, idx) => (
                      <span key={idx} className={t.type === "add" ? "diff-add" : t.type === "remove" ? "diff-remove" : ""}>
                        {t.text}
                      </span>
                    ))}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="muted">Select two different versions to see a diff.</p>
      )}

      <div className="card-header" style={{ marginTop: 20 }}>
        <span className="card-title">All versions</span>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Version</th>
            <th>Saved by</th>
            <th>Saved at</th>
            <th>ICD-10</th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <tr key={v.id}>
              <td>v{v.version_number}</td>
              <td>{v.saved_by_name}</td>
              <td>{new Date(v.saved_at).toLocaleString()}</td>
              <td>{v.icd10_codes.map((c) => c.code).join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
