import { Icd10Entry } from "./types";

const BASE = "/api";

export class SessionExpiredError extends Error {
  constructor() {
    super("Session expired");
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export class DeactivatedError extends Error {
  constructor() {
    super("Account has been deactivated");
  }
}

function getToken(): string | null {
  return localStorage.getItem("token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    // Session expired mid-action. We deliberately do NOT clear any caller-held form state
    // here -- the caller (see ReauthModal usage in EncounterEditor/NewEncounter) keeps whatever the
    // provider typed and retries after re-authenticating, so nothing is lost.
    throw new SessionExpiredError();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail: string = body.detail ?? res.statusText;
    if (res.status === 403 && detail.toLowerCase().includes("deactivat")) {
      throw new DeactivatedError();
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export interface SoapSections {
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
}

export interface SSEHandlers {
  onDelta: (chunk: string) => void;
  onDone: (finalSections: SoapSections, icd10Codes: Icd10Entry[]) => void;
  onNoClinicalContent: (raw: string) => void;
  onGenerationError: (message: string) => void;
}

/**
 * Manual SSE parsing over fetch (rather than EventSource) because EventSource cannot send
 * an Authorization header, and the generate endpoint is authenticated like everything else.
 */
export async function streamGenerateNote(
  encounterId: string,
  transcriptText: string,
  handlers: SSEHandlers,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/encounters/${encounterId}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ transcript_text: transcriptText }),
  });

  if (res.status === 401) throw new SessionExpiredError();
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // The SSE spec permits \n, \r, or \r\n as line terminators, and sse_starlette (the backend
    // library) emits \r\n. Normalizing here is what actually makes boundary detection below
    // work -- without it, indexOf("\n\n") never matches inside "\r\n\r\n" (no two consecutive
    // bare LFs exist in that sequence), so no event -- including "done" -- is ever parsed, and
    // the UI is stuck on "Generating..." forever even though the server finished normally.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let eventType = "message";
      const dataLines: string[] = [];
      for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        // A data value spanning multiple lines arrives as one "data:" line per line of the
        // original value; per the SSE spec these must be rejoined with "\n", not concatenated
        // directly, or multi-paragraph note text loses its line breaks.
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      const data = dataLines.join("\n");

      if (eventType === "delta") handlers.onDelta(data);
      else if (eventType === "done") {
        const { icd10_codes, ...sections } = JSON.parse(data);
        handlers.onDone(sections, icd10_codes ?? []);
      } else if (eventType === "no_clinical_content") handlers.onNoClinicalContent(data);
      else if (eventType === "generation_error") handlers.onGenerationError(data);
    }
  }
}
