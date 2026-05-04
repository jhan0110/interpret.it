"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { AttemptRecorder } from "@/lib/audio";
import type {
  SessionState as ContractSessionState,
  WSSegmentPlay,
  WSStateChange,
} from "@/lib/contracts";
import { WSClient } from "@/lib/ws";

/**
 * Active session UI. Per CLAUDE.md, this view MUST NOT render any text
 * representation of the audio content (no transcript, no subtitles, no
 * source text). State indicators and visual cues only.
 */
type Props = {
  sessionId: string;
  wsBaseUrl: string;
};

type CognitiveBand = "low" | "moderate" | "high" | "overloaded" | "idle";

const BAND_COLORS: Record<CognitiveBand, string> = {
  idle: "bg-zinc-700",
  low: "bg-emerald-500",
  moderate: "bg-yellow-400",
  high: "bg-orange-500",
  overloaded: "bg-red-600",
};

const STATE_LABELS: Record<ContractSessionState, string> = {
  idle: "Ready",
  listening: "Listening",
  recording: "Speak now",
  analyzing: "Analyzing",
  feedback: "Feedback",
  next_segment: "Next segment",
  complete: "Session complete",
};

export function SessionRunner({ sessionId, wsBaseUrl }: Props) {
  const [state, setState] = useState<ContractSessionState>("idle");
  const [band, setBand] = useState<CognitiveBand>("idle");
  const [currentSegmentId, setCurrentSegmentId] = useState<string | null>(null);
  const [currentAttemptId, setCurrentAttemptId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  const wsRef = useRef<WSClient | null>(null);
  const recorderRef = useRef<AttemptRecorder | null>(null);

  const url = useMemo(() => `${wsBaseUrl}/ws/sessions/${sessionId}`, [wsBaseUrl, sessionId]);

  useEffect(() => {
    const client = new WSClient(url);
    wsRef.current = client;

    client.on("state.change", (p: WSStateChange["payload"]) => setState(p.to));
    client.on("segment.play", (p: WSSegmentPlay["payload"]) => {
      setCurrentSegmentId(p.segment_id);
      setAudioUrl(p.audio_url);
    });
    client.on("prosody.result", (p) => setBand(p.cognitive_load_estimate));
    client.on("semantic.result", () => {
      // semantic.result intentionally not rendered as text here — review
      // route is the only place transcripts surface.
    });
    client.on("error", (p) => setError(p.detail));

    client.connect();
    client.sendSessionStart(sessionId);

    return () => {
      client.close();
      wsRef.current = null;
      recorderRef.current?.abort();
    };
  }, [url, sessionId]);

  async function requestSegment() {
    setError(null);
    setBand("idle");
    wsRef.current?.sendSegmentRequest(sessionId);
  }

  async function startRecording() {
    if (!currentSegmentId) return;
    const attemptId = uuidv4();
    setCurrentAttemptId(attemptId);

    const recorder = new AttemptRecorder();
    try {
      await recorder.start();
      recorderRef.current = recorder;
      wsRef.current?.sendRecordingBegin(sessionId, currentSegmentId, attemptId);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function stopRecording() {
    const recorder = recorderRef.current;
    if (!recorder || !currentSegmentId || !currentAttemptId) return;
    try {
      const { blob, durationMs } = await recorder.stop();
      wsRef.current?.submitAudio(
        {
          segment_id: currentSegmentId,
          attempt_id: currentAttemptId,
          audio_format: "opus/webm",
          byte_length: blob.size,
          duration_ms: durationMs,
          recorded_at: new Date().toISOString(),
        },
        blob
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      recorderRef.current = null;
    }
  }

  function completeSession() {
    wsRef.current?.sendSessionComplete(sessionId);
  }

  return (
    <div className="flex w-full max-w-2xl flex-col items-center gap-8 p-8 text-center">
      <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-zinc-400">
        <span aria-label="cognitive load" className={`h-3 w-3 rounded-full ${BAND_COLORS[band]}`} />
        <span>{STATE_LABELS[state]}</span>
      </div>

      <div className="text-2xl">
        {state === "listening" && <span aria-hidden>♪</span>}
        {state === "recording" && <span aria-hidden>● rec</span>}
        {state === "analyzing" && <span aria-hidden>⏳</span>}
        {state === "feedback" && <span aria-hidden>✓</span>}
        {state === "complete" && <span aria-hidden>—</span>}
      </div>

      {audioUrl && (state === "listening" || state === "feedback" || state === "next_segment") && (
        <audio autoPlay controls={false} src={audioUrl} />
      )}

      <div className="flex gap-3">
        {state === "idle" && (
          <button
            className="rounded-full bg-white px-6 py-3 text-black"
            onClick={requestSegment}
          >
            Begin
          </button>
        )}
        {(state === "listening" || state === "feedback") && (
          <button
            className="rounded-full bg-red-600 px-6 py-3"
            onClick={startRecording}
          >
            Record
          </button>
        )}
        {state === "recording" && (
          <button
            className="rounded-full bg-zinc-200 px-6 py-3 text-black"
            onClick={stopRecording}
          >
            Stop
          </button>
        )}
        {state === "feedback" && (
          <button
            className="rounded-full bg-zinc-700 px-6 py-3"
            onClick={requestSegment}
          >
            Next
          </button>
        )}
        {state !== "complete" && (
          <button
            className="rounded-full border border-zinc-600 px-6 py-3 text-zinc-300"
            onClick={completeSession}
          >
            End session
          </button>
        )}
      </div>

      {error && (
        <div role="alert" className="text-xs text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}
