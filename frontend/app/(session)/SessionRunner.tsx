"use client";

import { useEffect, useRef, useState } from "react";
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
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

/**
 * Active session UI. Per CLAUDE.md, no text is shown while the learner is
 * listening or recording — only state indicators and visual cues. After
 * each attempt the `feedback` state shows a full review-style breakdown.
 */
type Props = {
  sessionId: string;
};

type CognitiveBand = "low" | "moderate" | "high" | "overloaded" | "idle";

const BAND_COLORS: Record<CognitiveBand, string> = {
  idle: "bg-ink-faint",
  low: "bg-accent",
  moderate: "bg-[#B5901A]",
  high: "bg-warning",
  overloaded: "bg-critical",
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

export function SessionRunner({ sessionId }: Props) {
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

  const [segmentNumber, setSegmentNumber] = useState(0);

  const [delayMs, setDelayMs] = useState(0);
  const [remainingMs, setRemainingMs] = useState(0);

  const [audioDurationMs, setAudioDurationMs] = useState(0);
  const [audioElapsedMs, setAudioElapsedMs] = useState(0);
  const [audioEnded, setAudioEnded] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioFallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // When the 1.5s fallback fires before metadata loads, we mark the
  // audio "given up" so a late onCanPlay / onPlay can suppress
  // playback. Otherwise the element keeps loading in the background
  // and starts playing AFTER the UI has already moved past listening.
  const audioGivenUpRef = useRef<boolean>(false);
  // Track the post-`generation.complete` summary timers so unmount
  // doesn't fire setState on a torn-down component.
  const summaryHideRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const summaryFadeRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [showSummary, setShowSummary] = useState(false);
  const [summaryVisible, setSummaryVisible] = useState(false);

  const [recordingLevel, setRecordingLevel] = useState(0);
  const meterStreamRef = useRef<MediaStream | null>(null);
  // True when the meter opened its own getUserMedia stream (legacy
  // fallback path); false when we reused the recorder's stream and
  // therefore must NOT stop its tracks on teardown.
  const meterStreamOwnedRef = useRef<boolean>(false);

  const wsRef = useRef<WSClient | null>(null);
  const recorderRef = useRef<AttemptRecorder | null>(null);
  const delayIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelRafRef = useRef<number | null>(null);

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
    // Only stop tracks if we opened the stream ourselves. If we
    // reused the recorder's stream (H15), the recorder owns the
    // lifecycle and stopping here would also kill the recording.
    if (meterStreamOwnedRef.current) {
      meterStreamRef.current?.getTracks().forEach((t) => t.stop());
    }
    meterStreamRef.current = null;
    meterStreamOwnedRef.current = false;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    setRecordingLevel(0);
  }

  useEffect(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/sessions/${sessionId}`;
    const client = new WSClient(wsUrl);
    wsRef.current = client;

    client.on("state.change", (p: WSStateChange["payload"]) => {
      console.log("[WS] state.change", p.from, "->", p.to);
      setState(p.to);
      // Any error from before this transition is stale — clear it so
      // the user isn't staring at "session is still being prepared..."
      // ten minutes after the session actually became ready.
      setError(null);
    });
    client.on("segment.play", (p: WSSegmentPlay["payload"]) => {
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
      audioGivenUpRef.current = false;
      if (audioFallbackRef.current !== null) clearTimeout(audioFallbackRef.current);
      audioFallbackRef.current = setTimeout(() => {
        setAudioDurationMs((prev) => {
          if (prev === 0) {
            console.log("[audio] fallback: metadata not loaded, proceeding as ended");
            // Mark this audio as "given up" so any late onCanPlay /
            // onPlay handler suppresses playback. Without this, the
            // element kept loading in the background and started
            // playing AFTER the UI had moved past the listening phase
            // — audio audible after the progress bar terminated.
            audioGivenUpRef.current = true;
            const el = audioRef.current;
            if (el) {
              try {
                el.pause();
              } catch {
                // ignore — pause is best-effort
              }
            }
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
        if (p.scenario_summary) {
          setShowSummary(true);
          setSummaryVisible(true);
          if (summaryHideRef.current !== null) clearTimeout(summaryHideRef.current);
          if (summaryFadeRef.current !== null) clearTimeout(summaryFadeRef.current);
          summaryHideRef.current = setTimeout(() => {
            setSummaryVisible(false);
            summaryFadeRef.current = setTimeout(() => {
              setShowSummary(false);
              summaryFadeRef.current = null;
            }, 500);
            summaryHideRef.current = null;
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
      if (summaryHideRef.current !== null) {
        clearTimeout(summaryHideRef.current);
        summaryHideRef.current = null;
      }
      if (summaryFadeRef.current !== null) {
        clearTimeout(summaryFadeRef.current);
        summaryFadeRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

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
      // Safari still exposes the constructor as `webkitAudioContext`.
      // Type the window narrowly so we never need an `any` cast.
      type AudioCtxCtor = new () => AudioContext;
      const w = window as Window & {
        AudioContext?: AudioCtxCtor;
        webkitAudioContext?: AudioCtxCtor;
      };
      const AudioCtx = w.AudioContext ?? w.webkitAudioContext;
      if (!AudioCtx) return;

      // H15: prefer the recorder's already-open MediaStream so we
      // don't open the mic twice (Safari and some Linux/Pulse stacks
      // throw on a second `getUserMedia` for the same device).
      let stream: MediaStream | null = recorderRef.current?.stream ?? null;
      let ownedStream = false;
      if (stream === null) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              channelCount: 1,
            },
          });
          ownedStream = true;
        } catch {
          return;
        }
      }
      if (cancelled) {
        if (ownedStream) stream.getTracks().forEach((t) => t.stop());
        return;
      }

      meterStreamRef.current = stream;
      meterStreamOwnedRef.current = ownedStream;
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
    // Guard against a double-tap on the Record button (or any code path
    // that calls startRecording twice). Two sends of `recording.begin`
    // map to two `playback.finished` triggers; the second one hits the
    // state machine while it's already in `recording` and the gateway
    // surfaces "trigger 'playback.finished' not valid from state
    // 'recording'".
    if (recorderRef.current) return;
    const attemptId = uuidv4();
    setCurrentAttemptId(attemptId);

    const recorder = new AttemptRecorder();
    // Plant the ref BEFORE the await so a fast re-click can't race the
    // mic-permission round-trip.
    recorderRef.current = recorder;
    try {
      await recorder.start();
      wsRef.current?.sendRecordingBegin(sessionId, currentSegmentId, attemptId);
    } catch (e) {
      recorderRef.current = null;
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

      {/* Generation overlay */}
      {generating && (
        <Card
          role="status"
          aria-live="polite"
          className="w-full p-5"
        >
          <div className="mb-3 flex items-center justify-center gap-2 text-sm font-medium text-ink">
            {/* Spinner */}
            <svg
              className="h-4 w-4 animate-spin text-accent"
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
          <div className="mb-2 h-2 w-full overflow-hidden rounded-[2px] bg-paper-tint">
            <div
              className="h-2 bg-accent transition-all duration-300"
              style={{
                width: `${generation.target > 0 ? Math.round((generation.ready / generation.target) * 100) : 0}%`,
              }}
            />
          </div>
          <div className="text-xs text-ink-soft">
            {generation.ready} of {generation.target}
          </div>
        </Card>
      )}

      {/* Summary flash after generation.complete */}
      {showSummary && generation?.summary && (
        <div
          role="status"
          aria-live="polite"
          className={`w-full rounded-[2px] border border-accent p-4 text-sm text-ink-soft transition-opacity duration-500 ${
            summaryVisible ? "opacity-100" : "opacity-0"
          }`}
        >
          {generation.summary}
        </div>
      )}

      {generation?.state === "failed" && (
        <div
          role="alert"
          className="w-full rounded-[2px] border border-critical p-3 text-sm text-critical"
        >
          Generation failed. Try a smaller session or different topics.
        </div>
      )}

      {/* Cognitive load dot + segment counter */}
      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-ink-faint">
          <span
            aria-label={`Cognitive load: ${BAND_LABELS[band]}`}
            className={`h-3 w-3 rounded-[2px] ${BAND_COLORS[band]}`}
          />
          <span className="text-xs text-ink-soft">
            Load: <span className="text-ink">{BAND_LABELS[band]}</span>
          </span>
          <span>{STATE_LABELS[state]}</span>
        </div>

        {state !== "idle" && segmentNumber > 0 && (
          <div className="text-xs uppercase tracking-widest text-ink-faint">
            {generation?.target != null
              ? `Segment ${segmentNumber} of ${generation.target}`
              : `Segment ${segmentNumber}`}
          </div>
        )}
      </div>

      {/* Two-phase progress bar (audio then delay) */}
      {countdownActive && (
        <div className="w-full" role="timer" aria-label="Recording countdown">
          <div className="mb-1 text-xs uppercase tracking-widest text-ink-faint">
            {phaseLabel}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-[2px] bg-paper-tint">
            <div
              className={`h-1.5 transition-all duration-75 ${audioPhase ? "bg-ink-soft" : "bg-accent"}`}
              style={{ width: `${Math.round(overallProgress * 100)}%` }}
            />
          </div>
        </div>
      )}

      <div className="text-2xl">
        {state === "listening" && <span aria-hidden>♪</span>}
        {state === "recording" && (
          <div className="flex flex-col items-center gap-2" aria-label="Recording in progress">
            <span aria-hidden className="text-sm uppercase tracking-widest text-warning">● rec</span>
            {recordingLevel > 0 ? (
              <div className="h-2 w-40 overflow-hidden rounded-[2px] bg-paper-tint">
                <div
                  className="h-2 bg-warning transition-none"
                  style={{ width: `${Math.round(recordingLevel * 100)}%` }}
                />
              </div>
            ) : (
              <div className="h-2 w-2 animate-pulse rounded-[2px] bg-warning" aria-hidden />
            )}
          </div>
        )}
        {state === "analyzing" && <AnalyzingProgress />}
        {state === "feedback" && <span aria-hidden>✓</span>}
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
            // If we already gave up on this segment's audio (1.5s
            // fallback fired), do NOT report duration — that would
            // re-enable audioPhase and the progress bar would replay
            // alongside late audio.
            if (audioGivenUpRef.current) {
              const el = audioRef.current;
              if (el) {
                try {
                  el.pause();
                } catch {
                  // ignore
                }
              }
              return;
            }
            setAudioDurationMs(duration);
            if (audioFallbackRef.current !== null) {
              clearTimeout(audioFallbackRef.current);
              audioFallbackRef.current = null;
            }
          }}
          onPlay={() => {
            // Suppress late autoplay after the fallback gave up.
            if (audioGivenUpRef.current) {
              const el = audioRef.current;
              if (el) {
                try {
                  el.pause();
                } catch {
                  // ignore
                }
              }
            }
          }}
          onTimeUpdate={() => {
            if (audioGivenUpRef.current) return;
            setAudioElapsedMs((audioRef.current?.currentTime ?? 0) * 1000);
          }}
          onEnded={() => {
            if (audioGivenUpRef.current) return;
            const currentTime = audioRef.current?.currentTime ?? 0;
            console.log("[audio] ended at", currentTime);
            setAudioEnded(true);
          }}
        />
      )}

      {/* Feedback page — review-style breakdown of the just-finished attempt */}
      {state === "feedback" && (
        <Card className="w-full text-left">
          <AttemptFeedback
            semanticResult={semanticResult}
            prosodyResult={prosodyResult}
          />
        </Card>
      )}

      <div className="flex gap-3">
        {state === "idle" && (
          <Button
            variant="primary"
            onClick={requestSegment}
            disabled={generating}
            aria-disabled={generating}
            title={
              generating
                ? "Preparing your training set — wait for it to finish."
                : undefined
            }
          >
            {generating ? "Preparing…" : "Begin"}
          </Button>
        )}
        {(state === "listening" || state === "feedback") && (
          <Button
            variant="primary"
            onClick={startRecording}
            disabled={countdownActive}
            aria-disabled={countdownActive}
            className="session-record-btn"
          >
            Record
          </Button>
        )}
        {state === "recording" && (
          <Button variant="ghost" onClick={stopRecording}>
            Stop
          </Button>
        )}
        {state === "feedback" && (
          <Button variant="ghost" onClick={requestSegment}>
            Next
          </Button>
        )}

        {state === "complete" && (
          <Button
            variant="primary"
            onClick={() => router.push(`/review/${sessionId}`)}
          >
            View review
          </Button>
        )}

        {state !== "complete" && (
          <Button variant="ghost" onClick={completeSession}>
            End session
          </Button>
        )}
      </div>

      {error && (
        <div role="alert" className="text-xs text-critical">
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
      <div className="text-xs uppercase tracking-widest text-ink-soft">
        {label}
        <span className="ml-1 inline-block w-4 text-left text-ink-faint">
          {".".repeat(Math.floor((elapsed / 400) % 4))}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-[2px] bg-paper-tint">
        <div
          className="h-2 bg-accent transition-all duration-100"
          style={{ width: `${Math.min(95, Math.max(2, pct))}%` }}
        />
      </div>
      <div className="text-[10px] text-ink-faint">
        {(elapsed / 1000).toFixed(1)}s
      </div>
    </div>
  );
}
