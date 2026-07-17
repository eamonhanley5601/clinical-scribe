import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icd10SearchResult } from "../types";

/**
 * Compact search-with-dropdown widget rather than a permanently-tall results list -- the
 * results overlay the page below the input and disappear once you're done, instead of
 * claiming a fixed block of vertical space whether or not it's in use.
 */
export default function Icd10Search({ onSelect }: { onSelect: (result: Icd10SearchResult) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Icd10SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.get<Icd10SearchResult[]>(`/icd10/search?q=${encodeURIComponent(query)}`);
        setResults(res);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  const showDropdown = open && query.trim().length >= 2;

  function handleSelect(r: Icd10SearchResult) {
    onSelect(r);
    setQuery("");
    setResults([]);
    setOpen(false);
  }

  return (
    <div style={{ position: "relative", maxWidth: 360 }}>
      <label style={{ marginBottom: 5 }}>ICD-10 lookup</label>
      <input
        placeholder="Search a symptom or condition..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => {
          clearTimeout(closeTimerRef.current);
          setOpen(true);
        }}
        onBlur={() => {
          // Delay so a click on a result (which blurs the input first) still registers
          // before the dropdown disappears.
          closeTimerRef.current = setTimeout(() => setOpen(false), 150);
        }}
      />
      {showDropdown && (
        <div
          className="card"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 4,
            zIndex: 20,
            maxHeight: 320,
            overflowY: "auto",
            padding: 8,
          }}
        >
          {loading && <div className="muted" style={{ padding: "4px 8px" }}>Searching...</div>}
          {!loading &&
            results.map((r) => (
              <div key={r.code} className="icd10-result" onMouseDown={() => handleSelect(r)}>
                <span>
                  <span className="icd10-code">{r.code}</span>
                  {r.description}
                </span>
                <span className="muted">{(r.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          {!loading && results.length === 0 && <div className="muted" style={{ padding: "4px 8px" }}>No matching codes.</div>}
        </div>
      )}
    </div>
  );
}
