"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { v4 as uuidv4 } from "uuid";
import { AttemptRecorder } from "@/lib/audio";
import type {
  ProsodyResult,
  SemanticResult,
  SessionState as ContractSessionState,
  WSGenerationComplete,
  WSGenerationProgress,
  WSSegmentPlay,
  WSStateChange,
} from "@/lib/contracts";
import { WSClient } from "@/lib/ws";
import { AttemptFeedback } from "@/components/AttemptFeedback";

/**
 * Active session UI. Per CLAUDE.md, no text is shown while the learner is
 * listening or recording — only state indicators and visual cues. After
 * each attempt the `feedback` state shows a full review-style breakdown.
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

const BAND_LABELS: Record<CognitiveBand, string> = {
  idle: "—",
  low: "Low",
  moderate: "Moderate",
  high: "High",
  overloaded: "Overloaded",
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
  const router = useRouter();

  const [state, setState] = useState<ContractSessionState>("idle");
  const [band, setBand] = useState<CognitiveBand>("idle");
  const [currentSegmentId, setCurrentSegmentId] = useState<string | null>(null);
  const [currentAttemptId, setCurrentAttemptId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [semanticResult, setSemanticResult] = useState<SemanticResult | null>(null);
  const [prosodyResult, setProsodyResult] = useState<ProsodyResult | null>(null);
  const [generation, setGeneration] = useState<{
    state: "pending" | "ready" | "failed";
    ready: number;
    target: number;
    summary?: string | null;
  } | null>(null);

  // Item 2: segment counter
  const [segmentNumber, setSegmentNumber] = useState(0);

  // Item 3: calibrated-delay countdown
  const [delayMs, setDelayMs] = useState(0);
  const [remainingMs, setRemainingMs] = useState(0);

  // Audio phase tracking for two-phase progress bar
  const [audioDurationMs, setAudioDurationMs] = useState(0);
  const [audioElapsedMs, setAudioElapsedMs] = useState(0);
  const [audioEnded, setAudioEnded] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioFallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Item 1: generation complete summary — show for ~3s then fade out
  const [showSummary, setShowSummary] = useState(false);
  const [summaryVisible, setSummaryVisible] = useState(false);

  // Item 4: recording level meter (0–1)
  const [recordingLevel, setRecordingLevel] = useState(0);
  const meterStreamRef = useRef<MediaStream | null>(null);

  const wsRef = useRef<WSClient | null>(null);
  const recorderRef = useRef<AttemptRecorder | null>(null);
  const delayIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelRafRef = useRef<number | null>(null);

  const url = useMemo(() => `${wsBaseUrl}/ws/sessions/${sessionId}`, [wsBaseUrl, sessionId]);

  // Clear the delay countdown
  function clearDelayCountdown() {
    if (delayIntervalRef.current !== null) {
      clearInterval(delayIntervalRef.current);
      delayIntervalRef.current = null;
    }
  }

  // Tear down Web Audio level meter
  function teardownLevelMeter() {
    if (levelRafRef.current !== null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    meterStreamRef.current?.getTracks().forEach((t) => t.stop());
    meterStreamRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    setRecordingLevel(0);
  }

  useEffect(() => {
    const client = new WSClient(url);
    wsRef.current = client;

    client.on("state.change", (p: WSStateChange["payload"]) => {
      console.log("[WS] state.change", p.from, "->", p.to);
      setState(p.to);
    });
    client.on("segment.play", (p: WSSegmentPlay["payload"]) => {
      console.log("[WS] segment.play", p);
      setCurrentSegmentId(p.segment_id);
      setAudioUrl(p.audio_url);
      // New segment — clear the previous attempt's feedback.
      setSemanticResult(null);
      setProsodyResult(null);
      // Item 2: increment segment counter
      setSegmentNumber((n) => n + 1);
      // Item 3: capture delay for countdown; reset audio phase state
      setDelayMs(p.delay_ms ?? 0);
      setRemainingMs(p.delay_ms ?? 0);
      setAudioDurationMs(0);
      setAudioElapsedMs(0);
      setAudioEnded(false);
      // Fallback: if metadata doesn't load within 1.5s, treat audio as ended
      if (audioFallbackRef.current !== null) clearTimeout(audioFallbackRef.current);
      audioFallbackRef.current = setTimeout(() => {
        setAudioDurationMs((prev) => {
          if (prev === 0) {
            console.log("[audio] fallback: metadata not loaded, proceeding as ended");
            setAudioEnded(true);
          }
          return prev;
        });
        audioFallbackRef.current = null;
      }, 1500);
    });
    client.on("prosody.result", (p) => {
      console.log("[WS] prosody.result", p);
      setBand(p.cognitive_load_estimate);
      setProsodyResult(p);
    });
    client.on("semantic.result", (p) => {
      console.log("[WS] semantic.result", p);
      setSemanticResult(p);
    });
    client.on(
      "generation.progress",
      (p: WSGenerationProgress["payload"]) => {
        console.log("[WS] generation.progress", p);
        setGeneration({
          state: p.state,
          ready: p.ready,
          target: p.target,
        });
      },
    );
    client.on(
      "generation.complete",
      (p: WSGenerationComplete["payload"]) => {
        console.log("[WS] generation.complete", p);
        setGeneration({
          state: "ready",
          ready: p.count,
          target: p.count,
          summary: p.scenario_summary,
        });
        // Item 1: show summary for ~3s then fade
        if (p.scenario_summary) {
          setShowSummary(true);
          setSummaryVisible(true);
          setTimeout(() => {
            setSummaryVisible(false);
            setTimeout(() => setShowSummary(false), 500);
          }, 3000);
        }
      },
    );
    client.on("error", (p) => setError(p.detail));

    client.connect();
    client.sendSessionStart(sessionId);

    return () => {
      client.close();
      wsRef.current = null;
      recorderRef.current?.abort();
      clearDelayCountdown();
      teardownLevelMeter();
      if (audioFallbackRef.current !== null) {
        clearTimeout(audioFallbackRef.current);
        audioFallbackRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, sessionId]);

  // Item 3: run countdown after audio ends (not at audio start)
  useEffect(() => {
    clearDelayCountdown();
    if (audioEnded && state === "listening" && delayMs > 0) {
      const startedAt = performance.now();
      delayIntervalRef.current = setInterval(() => {
        const elapsed = performance.now() - startedAt;
        const left = Math.max(0, delayMs - elapsed);
        setRemainingMs(left);
        if (left === 0) {
          clearDelayCountdown();
        }
      }, 50);
    } else if (!audioEnded) {
      setRemainingMs(delayMs);
    }
    return clearDelayCountdown;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioEnded, state, delayMs]);

  // Item 4: set up level meter while recording
  useEffect(() => {
    if (state !== "recording") {
      teardownLevelMeter();
      return;
    }

    // Try to attach to the active stream from the recorder
    let cancelled = false;
    const attachMeter = async () => {
      // Give the recorder a tick to initialise
      await new Promise<void>((r) => setTimeout(r, 0));
      if (cancelled) return;

      // Attempt to pull the stream from the MediaRecorder internals.
      // AttemptRecorder keeps `stream` private, so we use getUserMedia as a
      // fallback tap — we ask for the same constraints, get the same device.
      if (typeof window === "undefined") return;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const AudioCtx: typeof AudioContext =
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).AudioContext ?? (window as any).webkitAudioContext;
      if (!AudioCtx) return;

      let stream: MediaStream | null = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        });
      } catch {
        // If we can't get mic access for the analyser, show a pulsing dot instead
        return;
      }
      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      meterStreamRef.current = stream;
      const ctx = new AudioCtx();
      audioContextRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const src = ctx.createMediaStreamSource(stream);
      src.connect(analyser);

      const buf = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(buf);
        const avg = buf.reduce((s, v) => s + v, 0) / buf.length;
        setRecordingLevel(avg / 255);
        levelRafRef.current = requestAnimationFrame(tick);
      };
      levelRafRef.current = requestAnimationFrame(tick);
    };

    attachMeter();
    return () => {
      cancelled = true;
      teardownLevelMeter();
    };
  // Only re-run when recording state changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

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
      const { blob, durationMs, mimeType } = await recorder.stop();
      wsRef.current?.submitAudio(
        {
          segment_id: currentSegmentId,
          attempt_id: currentAttemptId,
          audio_format: mimeType,
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

  const generating =
    generation !== null &&
    generation.state === "pending" &&
    state === "idle";

  // Two-phase bar: audio phase then delay phase
  const audioPhase = audioDurationMs > 0 && !audioEnded;
  const delayPhase = audioEnded && delayMs > 0 && remainingMs > 50;
  const countdownActive = state === "listening" && (audioPhase || delayPhase);

  const phaseLabel = audioPhase
    ? "Listening"
    : `Recording in ${(remainingMs / 1000).toFixed(1)}s`;

  const audioFrac = audioDurationMs > 0 ? Math.min(1, audioElapsedMs / audioDurationMs) : 0;
  const delayFrac = delayMs > 0 ? 1 - remainingMs / delayMs : 1;
  const overallProgress = audioPhase ? audioFrac * 0.5 : 0.5 + delayFrac * 0.5;

  return (
    <div className="flex w-full max-w-2xl flex-col items-center gap-8 p-8 text-center">

      {/* ── Item 1: Generation overlay ── */}
      {generating && (
        <div
          role="status"
          aria-live="polite"
          className="w-full rounded-lg border border-zinc-700 bg-zinc-900/60 p-5 shadow-md"
        >
          <div className="mb-3 flex items-center justify-center gap-2 text-sm font-medium text-zinc-100">
            {/* Spinner */}
            <svg
              className="h-4 w-4 animate-spin text-zinc-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
            Preparing your training set…
          </div>

          {/* Progress bar */}
          <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-zinc-700">
            <div
              className="h-2 rounded-full bg-emerald-500 transition-all duration-300"
              style={{
                width: `${generation.target > 0 ? Math.round((generation.ready / generation.target) * 100) : 0}%`,
              }}
            />
          </div>
          <div className="text-xs text-zinc-400">
            {generation.ready} of {generation.target}
          </div>
        </div>
      )}

      {/* Item 1: summary flash after generation.complete */}
      {showSummary && generation?.summary && (
        <div
          role="status"
          aria-live="polite"
          className={`w-full rounded-lg border border-emerald-700 bg-emerald-900/30 p-4 text-sm text-emerald-200 transition-opacity duration-500 ${
            summaryVisible ? "opacity-100" : "opacity-0"
          }`}
        >
          {generation.summary}
        </div>
      )}

      {generation?.state === "failed" && (
        <div
          role="alert"
          className="w-full rounded border border-red-700 bg-red-900/40 p-3 text-sm text-red-200"
        >
          Generation failed. Try a smaller session or different topics.
        </div>
      )}

      {/* ── Item 2 + A11y: cognitive load dot + segment counter ── */}
      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-zinc-400">
          <span
            aria-label={`Cognitive load: ${BAND_LABELS[band]}`}
            className={`h-3 w-3 rounded-full ${BAND_COLORS[band]}`}
          />
          {/* Item 6: visible text label for sighted users */}
          <span className="text-xs text-zinc-500">
            Load: <span className="text-zinc-300">{BAND_LABELS[band]}</span>
          </span>
          <span>{STATE_LABELS[state]}</span>
        </div>

        {/* Item 2: segment progress */}
        {state !== "idle" && segmentNumber > 0 && (
          <div className="text-xs uppercase tracking-widest text-zinc-500">
            {generation?.target != null
              ? `Segment ${segmentNumber} of ${generation.target}`
              : `Segment ${segmentNumber}`}
          </div>
        )}
      </div>

      {/* ── Item 3: two-phase progress bar (audio then delay) ── */}
      {countdownActive && (
        <div className="w-full" role="timer" aria-label="Recording countdown">
          <div className="mb-1 text-xs uppercase tracking-widest text-zinc-500">
            {phaseLabel}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-700">
            <div
              className={`h-1.5 rounded-full transition-all duration-75 ${audioPhase ? "bg-blue-400" : "bg-yellow-400"}`}
              style={{ width: `${Math.round(overallProgress * 100)}%` }}
            />
          </div>
        </div>
      )}

      <div className="text-2xl">
        {state === "listening" && <span aria-hidden>♪</span>}
        {/* Item 4: recording level meter replaces static ● rec */}
        {state === "recording" && (
          <div className="flex flex-col items-center gap-2" aria-label="Recording in progress">
            <span aria-hidden className="text-sm uppercase tracking-widest text-red-400">● rec</span>
            {/* Level bar — or pulsing dot if AudioContext unavailable */}
            {recordingLevel > 0 ? (
              <div className="h-2 w-40 overflow-hidden rounded-full bg-zinc-700">
                <div
                  className="h-2 rounded-full bg-red-500 transition-none"
                  style={{ width: `${Math.round(recordingLevel * 100)}%` }}
                />
              </div>
            ) : (
              <div className="h-2 w-2 animate-pulse rounded-full bg-red-500" aria-hidden />
            )}
          </div>
        )}
        {state === "analyzing" && <AnalyzingProgress />}
        {state === "feedback" && <span aria-hidden>✓</span>}
        {/* Item 5: complete state handled below */}
      </div>

      {audioUrl && state === "listening" && (
        <audio
          key={audioUrl}
          autoPlay
          controls={false}
          src={audioUrl}
          ref={audioRef}
          onLoadedMetadata={() => {
            const duration = (audioRef.current?.duration ?? 0) * 1000;
            console.log("[audio] metadata loaded, duration=", duration);
            setAudioDurationMs(duration);
            if (audioFallbackRef.current !== null) {
              clearTimeout(audioFallbackRef.current);
              audioFallbackRef.current = null;
            }
          }}
          onTimeUpdate={() => {
            setAudioElapsedMs((audioRef.current?.currentTime ?? 0) * 1000);
          }}
          onEnded={() => {
            const currentTime = audioRef.current?.currentTime ?? 0;
            console.log("[audio] ended at", currentTime);
            setAudioEnded(true);
          }}
        />
      )}

      {/* Feedback page — review-style breakdown of the just-finished attempt */}
      {state === "feedback" && (
        <div className="w-full rounded-lg bg-white p-6 text-left text-black">
          <AttemptFeedback
            semanticResult={semanticResult}
            prosodyResult={prosodyResult}
          />
        </div>
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
            className="rounded-full bg-red-600 px-6 py-3 disabled:cursor-not-allowed disabled:opacity-40"
            onClick={startRecording}
            disabled={countdownActive}
            aria-disabled={countdownActive}
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

        {/* Item 5: "View review" CTA on complete */}
        {state === "complete" && (
          <button
            className="rounded-full bg-emerald-600 px-6 py-3 text-white hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-400"
            onClick={() => router.push(`/review/${sessionId}`)}
          >
            View review
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

// Analyzing progress — pipeline doesn't emit per-stage events, so we
// time-animate against known SLA targets (~12s for the semantic full path).
// Bar caps at 95% until state transitions out of "analyzing".
const STAGES = [
  { until: 2000, label: "Transcribing audio", endPct: 25 },
  { until: 6000, label: "Checking interpretation", endPct: 65 },
  { until: 12000, label: "Generating feedback", endPct: 95 },
] as const;

function AnalyzingProgress() {
  const startedAtRef = useRef(performance.now());
  const [elapsed, setElapsed] = useState(0);
  const prevLabelRef = useRef<string>("");

  useEffect(() => {
    console.log("[analyzing] start");
    startedAtRef.current = performance.now();
    const id = setInterval(() => {
      setElapsed(performance.now() - startedAtRef.current);
    }, 100);
    return () => {
      clearInterval(id);
      console.log("[analyzing] done after", (performance.now() - startedAtRef.current).toFixed(0), "ms");
    };
  }, []);

  let label = STAGES[STAGES.length - 1].label;
  let pct = 95;
  let prevUntil = 0;
  let prevPct = 0;
  for (const stage of STAGES) {
    if (elapsed < stage.until) {
      const span = stage.until - prevUntil;
      const t = (elapsed - prevUntil) / span;
      pct = prevPct + (stage.endPct - prevPct) * t;
      label = stage.label;
      break;
    }
    prevUntil = stage.until;
    prevPct = stage.endPct;
  }

  if (label !== prevLabelRef.current) {
    console.log("[analyzing] stage", label, "pct=", pct);
    prevLabelRef.current = label;
  }

  return (
    <div className="flex w-72 flex-col items-center gap-2" aria-label="Analyzing">
      <div className="text-xs uppercase tracking-widest text-zinc-400">
        {label}
        <span className="ml-1 inline-block w-4 text-left text-zinc-600">
          {".".repeat(Math.floor((elapsed / 400) % 4))}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-2 rounded-full bg-emerald-500 transition-all duration-100"
          style={{ width: `${Math.min(95, Math.max(2, pct))}%` }}
        />
      </div>
      <div className="text-[10px] text-zinc-600">
        {(elapsed / 1000).toFixed(1)}s
      </div>
    </div>
  );
}
