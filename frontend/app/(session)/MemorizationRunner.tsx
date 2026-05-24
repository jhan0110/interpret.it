"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { v4 as uuidv4 } from "uuid";
import { AttemptRecorder } from "@/lib/audio";
import type {
  AudioSubmission,
  ProsodyResult,
  ReplayDeniedReason,
  SemanticResult,
  ServerMessage,
  SessionState as ContractSessionState,
  WSAudioSubmitHeader,
  WSGenerationComplete,
  WSGenerationProgress,
  WSRecordingBegin,
  WSReplayRequest,
  WSSegmentPlay,
  WSSegmentRequest,
  WSSessionComplete,
  WSSessionStart,
  WSStateChange,
} from "@/lib/contracts";
import { AttemptFeedback } from "@/components/AttemptFeedback";

type Props = {
  sessionId: string;
  wsBaseUrl: string;
  replaysBudget: number;
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
  recording: "Recall now",
  analyzing: "Analyzing",
  feedback: "Feedback",
  next_segment: "Next segment",
  complete: "Session complete",
};

const REPLAY_DENIED_MESSAGES: Record<ReplayDeniedReason, string> = {
  budget_exhausted: "No replays left for this session.",
  already_replayed: "This segment has already been replayed.",
  wrong_mode: "Replays aren't available in this mode.",
  invalid_state: "Replay isn't available right now.",
};

const BACKOFF_CAP_MS = 30_000;

export function MemorizationRunner({
  sessionId,
  wsBaseUrl,
  replaysBudget,
}: Props) {
  const router = useRouter();

  const [state, setState] = useState<ContractSessionState>("idle");
  const [band, setBand] = useState<CognitiveBand>("idle");
  const [currentSegmentId, setCurrentSegmentId] = useState<string | null>(null);
  const [currentAttemptId, setCurrentAttemptId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [semanticResult, setSemanticResult] = useState<SemanticResult | null>(
    null,
  );
  const [prosodyResult, setProsodyResult] = useState<ProsodyResult | null>(
    null,
  );
  const [generation, setGeneration] = useState<{
    state: "pending" | "ready" | "failed";
    ready: number;
    target: number;
    summary?: string | null;
  } | null>(null);

  const [segmentNumber, setSegmentNumber] = useState(0);
  const [delayMs, setDelayMs] = useState(0);
  const [remainingMs, setRemainingMs] = useState(0);

  const [audioDurationMs, setAudioDurationMs] = useState(0);
  const [audioElapsedMs, setAudioElapsedMs] = useState(0);
  const [audioEnded, setAudioEnded] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioFallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [showSummary, setShowSummary] = useState(false);
  const [summaryVisible, setSummaryVisible] = useState(false);

  const [recordingLevel, setRecordingLevel] = useState(0);
  const meterStreamRef = useRef<MediaStream | null>(null);

  const [replaysRemaining, setReplaysRemaining] = useState<number>(replaysBudget);
  const [replayedThisSegment, setReplayedThisSegment] = useState(false);
  const [replayDenied, setReplayDenied] = useState<string | null>(null);
  const replayDeniedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  const wsRef = useRef<WebSocket | null>(null);
  const wsClosedRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recorderRef = useRef<AttemptRecorder | null>(null);
  const delayIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelRafRef = useRef<number | null>(null);

  const url = useMemo(
    () => `${wsBaseUrl}/ws/sessions/${sessionId}`,
    [wsBaseUrl, sessionId],
  );

  function clearDelayCountdown() {
    if (delayIntervalRef.current !== null) {
      clearInterval(delayIntervalRef.current);
      delayIntervalRef.current = null;
    }
  }

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

  function sendEnvelope(
    msg:
      | WSSessionStart
      | WSSegmentRequest
      | WSRecordingBegin
      | WSAudioSubmitHeader
      | WSReplayRequest
      | WSSessionComplete,
  ) {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }

  function submitAudio(submission: AudioSubmission, blob: Blob) {
    const ws = wsRef.current;
    if (ws?.readyState !== WebSocket.OPEN) return;
    const header: WSAudioSubmitHeader = {
      type: "audio.submit_header",
      ts: new Date().toISOString(),
      payload: submission,
    };
    ws.send(JSON.stringify(header));
    ws.send(blob);
  }

  function showReplayDenied(reason: ReplayDeniedReason) {
    if (replayDeniedTimerRef.current !== null) {
      clearTimeout(replayDeniedTimerRef.current);
    }
    setReplayDenied(REPLAY_DENIED_MESSAGES[reason]);
    replayDeniedTimerRef.current = setTimeout(() => {
      setReplayDenied(null);
      replayDeniedTimerRef.current = null;
    }, 3000);
  }

  function handleServerMessage(msg: ServerMessage) {
    switch (msg.type) {
      case "state.change": {
        console.log("[WS] state.change", msg.payload.from, "->", msg.payload.to);
        setState(msg.payload.to);
        break;
      }
      case "segment.play": {
        const p: WSSegmentPlay["payload"] = msg.payload;
        console.log("[WS] segment.play", p);
        setCurrentSegmentId(p.segment_id);
        setAudioUrl(p.audio_url);
        setSemanticResult(null);
        setProsodyResult(null);
        setSegmentNumber((n) => n + 1);
        setDelayMs(p.delay_ms ?? 0);
        setRemainingMs(p.delay_ms ?? 0);
        setAudioDurationMs(0);
        setAudioElapsedMs(0);
        setAudioEnded(false);
        setReplayedThisSegment(false);
        setReplayDenied(null);
        if (audioFallbackRef.current !== null)
          clearTimeout(audioFallbackRef.current);
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
        break;
      }
      case "prosody.result": {
        console.log("[WS] prosody.result", msg.payload);
        setBand(msg.payload.cognitive_load_estimate);
        setProsodyResult(msg.payload);
        break;
      }
      case "semantic.result": {
        console.log("[WS] semantic.result", msg.payload);
        setSemanticResult(msg.payload);
        break;
      }
      case "generation.progress": {
        const p: WSGenerationProgress["payload"] = msg.payload;
        setGeneration({ state: p.state, ready: p.ready, target: p.target });
        break;
      }
      case "generation.complete": {
        const p: WSGenerationComplete["payload"] = msg.payload;
        setGeneration({
          state: "ready",
          ready: p.count,
          target: p.count,
          summary: p.scenario_summary,
        });
        if (p.scenario_summary) {
          setShowSummary(true);
          setSummaryVisible(true);
          setTimeout(() => {
            setSummaryVisible(false);
            setTimeout(() => setShowSummary(false), 500);
          }, 3000);
        }
        break;
      }
      case "replay.granted": {
        console.log("[WS] replay.granted", msg.payload);
        setReplaysRemaining(msg.payload.replays_remaining);
        setReplayedThisSegment(true);
        const a = audioRef.current;
        if (a && audioUrlRef.current) {
          try {
            a.currentTime = 0;
            void a.play();
          } catch {
            // ignore
          }
          setAudioEnded(false);
        }
        break;
      }
      case "replay.denied": {
        console.log("[WS] replay.denied", msg.payload);
        setReplaysRemaining(msg.payload.replays_remaining);
        setReplayedThisSegment(true);
        showReplayDenied(msg.payload.reason);
        break;
      }
      case "error": {
        setError(msg.payload.detail);
        break;
      }
      default:
        break;
    }
  }

  const audioUrlRef = useRef<string | null>(null);
  useEffect(() => {
    audioUrlRef.current = audioUrl;
  }, [audioUrl]);

  useEffect(() => {
    wsClosedRef.current = false;

    const open = () => {
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        const startMsg: WSSessionStart = {
          type: "session.start",
          ts: new Date().toISOString(),
          payload: { session_id: sessionId },
        };
        ws.send(JSON.stringify(startMsg));
      };

      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) return;
        try {
          const msg = JSON.parse(ev.data as string) as ServerMessage;
          handleServerMessage(msg);
        } catch {
          // ignore malformed
        }
      };

      ws.onclose = () => {
        if (wsClosedRef.current) return;
        const delay = Math.min(
          BACKOFF_CAP_MS,
          1_000 * Math.pow(2, reconnectAttemptRef.current),
        );
        reconnectAttemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(open, delay);
      };

      ws.onerror = () => {
        // onclose handles reconnect
      };
    };

    open();

    return () => {
      wsClosedRef.current = true;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
      recorderRef.current?.abort();
      clearDelayCountdown();
      teardownLevelMeter();
      if (audioFallbackRef.current !== null) {
        clearTimeout(audioFallbackRef.current);
        audioFallbackRef.current = null;
      }
      if (replayDeniedTimerRef.current !== null) {
        clearTimeout(replayDeniedTimerRef.current);
        replayDeniedTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, sessionId]);

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

  useEffect(() => {
    if (state !== "recording") {
      teardownLevelMeter();
      return;
    }

    let cancelled = false;
    const attachMeter = async () => {
      await new Promise<void>((r) => setTimeout(r, 0));
      if (cancelled) return;

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  async function requestSegment() {
    setError(null);
    setBand("idle");
    const msg: WSSegmentRequest = {
      type: "segment.request",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId },
    };
    sendEnvelope(msg);
  }

  async function startRecording() {
    if (!currentSegmentId) return;
    const attemptId = uuidv4();
    setCurrentAttemptId(attemptId);

    const recorder = new AttemptRecorder();
    try {
      await recorder.start();
      recorderRef.current = recorder;
      const msg: WSRecordingBegin = {
        type: "recording.begin",
        ts: new Date().toISOString(),
        payload: {
          session_id: sessionId,
          segment_id: currentSegmentId,
          attempt_id: attemptId,
        },
      };
      sendEnvelope(msg);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function stopRecording() {
    const recorder = recorderRef.current;
    if (!recorder || !currentSegmentId || !currentAttemptId) return;
    try {
      const { blob, durationMs, mimeType } = await recorder.stop();
      submitAudio(
        {
          segment_id: currentSegmentId,
          attempt_id: currentAttemptId,
          audio_format: mimeType,
          byte_length: blob.size,
          duration_ms: durationMs,
          recorded_at: new Date().toISOString(),
        },
        blob,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      recorderRef.current = null;
    }
  }

  function requestReplay() {
    if (!currentAttemptId) return;
    if (replayedThisSegment) return;
    if (replaysRemaining <= 0) {
      showReplayDenied("budget_exhausted");
      return;
    }
    const msg: WSReplayRequest = {
      type: "replay.request",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId, attempt_id: currentAttemptId },
    };
    sendEnvelope(msg);
  }

  function completeSession() {
    const msg: WSSessionComplete = {
      type: "session.complete",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId },
    };
    sendEnvelope(msg);
  }

  const generating =
    generation !== null && generation.state === "pending" && state === "idle";

  const audioPhase = audioDurationMs > 0 && !audioEnded;
  const delayPhase = audioEnded && delayMs > 0 && remainingMs > 50;
  const countdownActive = state === "listening" && (audioPhase || delayPhase);

  const phaseLabel = audioPhase
    ? "Listening"
    : `Recall in ${(remainingMs / 1000).toFixed(1)}s`;

  const audioFrac =
    audioDurationMs > 0 ? Math.min(1, audioElapsedMs / audioDurationMs) : 0;
  const delayFrac = delayMs > 0 ? 1 - remainingMs / delayMs : 1;
  const overallProgress = audioPhase ? audioFrac * 0.5 : 0.5 + delayFrac * 0.5;

  const replayShown = state === "listening" || state === "recording";
  const replayDisabled =
    replayedThisSegment ||
    replaysRemaining <= 0 ||
    !currentAttemptId ||
    (state !== "listening" && state !== "recording");

  return (
    <div className="flex w-full max-w-2xl flex-col items-center gap-8 p-8 text-center">
      {generating && (
        <div
          role="status"
          aria-live="polite"
          className="w-full rounded-lg border border-zinc-700 bg-zinc-900/60 p-5 shadow-md"
        >
          <div className="mb-3 flex items-center justify-center gap-2 text-sm font-medium text-zinc-100">
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
            Preparing your memorization set…
          </div>

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

      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-zinc-400">
          <span
            aria-label={`Cognitive load: ${BAND_LABELS[band]}`}
            className={`h-3 w-3 rounded-full ${BAND_COLORS[band]}`}
          />
          <span className="text-xs text-zinc-500">
            Load: <span className="text-zinc-300">{BAND_LABELS[band]}</span>
          </span>
          <span>{STATE_LABELS[state]}</span>
        </div>

        {state !== "idle" && segmentNumber > 0 && (
          <div className="text-xs uppercase tracking-widest text-zinc-500">
            {generation?.target != null
              ? `Segment ${segmentNumber} of ${generation.target}`
              : `Segment ${segmentNumber}`}
          </div>
        )}
      </div>

      {countdownActive && (
        <div className="w-full" role="timer" aria-label="Recall countdown">
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
        {state === "recording" && (
          <div className="flex flex-col items-center gap-2" aria-label="Recall in progress">
            <span aria-hidden className="text-sm uppercase tracking-widest text-red-400">
              ● rec
            </span>
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
      </div>

      {audioUrl && (state === "listening" || state === "recording") && (
        <audio
          key={audioUrl}
          autoPlay={state === "listening"}
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

      {replayShown && (
        <div className="flex flex-col items-center gap-1">
          <button
            type="button"
            onClick={requestReplay}
            disabled={replayDisabled}
            className="rounded-full border border-zinc-500 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Replay segment
          </button>
          <div className="text-[11px] uppercase tracking-widest text-zinc-500">
            {replaysRemaining} {replaysRemaining === 1 ? "replay" : "replays"} left
          </div>
          {replayDenied && (
            <div role="alert" className="text-xs text-amber-400">
              {replayDenied}
            </div>
          )}
        </div>
      )}

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
            Recall
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

const STAGES = [
  { until: 2000, label: "Transcribing audio", endPct: 25 },
  { until: 6000, label: "Scoring recall", endPct: 65 },
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
      console.log(
        "[analyzing] done after",
        (performance.now() - startedAtRef.current).toFixed(0),
        "ms",
      );
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
