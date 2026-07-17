import { useEffect, useRef, useState } from "react";

type Status = "idle" | "recording" | "denied" | "unsupported";

const SpeechRecognitionCtor = window.SpeechRecognition ?? window.webkitSpeechRecognition;

export function appendTranscriptChunk(existing: string, chunk: string): string {
  if (!existing) return chunk;
  return existing.endsWith(" ") || existing.endsWith("\n") ? existing + chunk : `${existing} ${chunk}`;
}

/**
 * Optional voice-to-transcript input, alongside typing/pasting (never a replacement for it).
 * Uses the browser's built-in Web Speech API rather than any paid transcription service --
 * zero signup, zero API key, zero backend involvement, consistent with this project's "must be
 * free" constraint. Tradeoff, disclosed in the UI below: Chrome/Edge only, and recognition isn't
 * actually fully on-device -- the browser vendor's own speech backend produces the text.
 */
export default function VoiceRecorder({
  onTranscript,
  disabled,
}: {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}) {
  const [status, setStatus] = useState<Status>(SpeechRecognitionCtor ? "idle" : "unsupported");
  const recognitionRef = useRef<InstanceType<NonNullable<typeof SpeechRecognitionCtor>> | null>(null);
  // True until the doctor clicks Stop -- this is what distinguishes an intentional stop from the
  // browser's own silence-triggered auto-stop in onend, which should instead auto-restart.
  const wantRecordingRef = useRef(false);

  function stopRecording() {
    wantRecordingRef.current = false;
    recognitionRef.current?.stop();
  }

  function startRecording() {
    if (!SpeechRecognitionCtor) return;
    wantRecordingRef.current = true;
    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        // Only finalized results are passed through -- interim results are still being revised
        // by the recognizer and would otherwise produce duplicate/garbled text.
        if (result.isFinal) {
          const text = result[0].transcript.trim();
          if (text) onTranscript(text);
        }
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        // Must clear this before onend fires, or the auto-restart below will keep retrying
        // against a microphone permission that was just denied.
        wantRecordingRef.current = false;
        setStatus("denied");
      }
      // Other errors (no-speech, network, aborted, ...) are routine/transient -- onend handles
      // recovery (auto-restart while still wanted, or settling to idle otherwise).
    };

    recognition.onend = () => {
      if (wantRecordingRef.current) {
        // Browser-driven silence cutoff, not the doctor stopping -- keep dictation going.
        try {
          recognition.start();
        } catch {
          // Restarting while a session is mid-teardown can throw InvalidStateError; drop the
          // attempt rather than crash -- the doctor can just click record again.
          setStatus("idle");
        }
      } else {
        setStatus("idle");
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
    setStatus("recording");
  }

  useEffect(() => {
    // Navigating away mid-dictation shouldn't leave a recognition session running against a
    // torn-down component.
    return () => {
      wantRecordingRef.current = false;
      recognitionRef.current?.stop();
    };
  }, []);

  useEffect(() => {
    if (disabled && status === "recording") stopRecording();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled]);

  if (status === "unsupported") {
    return <span className="muted">Voice dictation isn't available in this browser — try Chrome or Edge.</span>;
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {status === "recording" && (
        <span className="pill recording">
          <span className="rec-dot" />
          Recording…
        </span>
      )}
      <button
        type="button"
        className="ghost"
        disabled={disabled}
        onClick={() => (status === "recording" ? stopRecording() : startRecording())}
      >
        {status === "recording" ? "Stop recording" : "🎤 Record"}
      </button>
      {status === "denied" && (
        <span className="muted">Microphone access denied — check your browser's site permissions.</span>
      )}
      {status === "idle" && <span className="muted">Uses your browser's built-in speech recognition.</span>}
    </div>
  );
}
