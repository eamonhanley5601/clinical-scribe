export interface SoapDraft {
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
}

const MARKERS: [keyof SoapDraft, string][] = [
  ["subjective", "##SUBJECTIVE##"],
  ["objective", "##OBJECTIVE##"],
  ["assessment", "##ASSESSMENT##"],
  ["plan", "##PLAN##"],
];

export const NO_CLINICAL_CONTENT_MARKER = "##NO_CLINICAL_CONTENT##";

/** Tolerant of partial/streaming text: whichever markers have arrived so far get sectioned off,
 * the most recent one keeps absorbing new text as it streams in. */
export function parsePartialSoap(accumulated: string): SoapDraft {
  const found = MARKERS.map(([key, marker]) => ({ key, marker, index: accumulated.indexOf(marker) })).filter(
    (m) => m.index !== -1,
  );
  found.sort((a, b) => a.index - b.index);

  const result: SoapDraft = { subjective: "", objective: "", assessment: "", plan: "" };
  for (let i = 0; i < found.length; i++) {
    const start = found[i].index + found[i].marker.length;
    const end = i + 1 < found.length ? found[i + 1].index : accumulated.length;
    result[found[i].key] = accumulated.slice(start, end).trim();
  }
  return result;
}
