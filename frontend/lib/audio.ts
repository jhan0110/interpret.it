/**
 * MediaRecorder wrapper for opus/webm capture.
 *
 * The recorder collects a single complete Blob per attempt — no streaming,
 * no PCM. The browser MediaRecorder API natively emits Opus/WebM, which
 * matches `AudioSubmission.audio_format = "opus/webm"`.
 *
 * Usage:
 *   const r = new AttemptRecorder();
 *   await r.start();             // grants mic + opens recorder
 *   // ... user speaks ...
 *   const { blob, durationMs } = await r.stop();
 */

// Ordered preference: Opus/WebM (Chrome/Firefox), then MP4/AAC (Safari),
// then any audio/* MediaRecorder will accept. Whisper handles all of these.
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4;codecs=mp4a.40.2",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

export type RecordingResult = {
  blob: Blob;
  durationMs: number;
  mimeType: string;
};

export class AttemptRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: BlobPart[] = [];
  private stream: MediaStream | null = null;
  private startedAt = 0;
  private resolveStop: ((r: RecordingResult) => void) | null = null;
  private rejectStop: ((err: Error) => void) | null = null;

  static isSupported(): boolean {
    if (typeof window === "undefined") return false;
    if (!("MediaRecorder" in window)) return false;
    return MIME_CANDIDATES.some((m) => MediaRecorder.isTypeSupported(m));
  }

  private pickMime(): string {
    for (const m of MIME_CANDIDATES) {
      if (MediaRecorder.isTypeSupported(m)) return m;
    }
    throw new Error(
      "No MediaRecorder MIME type supported — try Chrome, Firefox, Edge, or Safari 14.1+",
    );
  }

  async start(): Promise<void> {
    if (this.mediaRecorder) {
      throw new Error("recorder already started");
    }
    if (typeof navigator === "undefined" || !navigator.mediaDevices) {
      throw new Error("mediaDevices unavailable in this environment");
    }

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
      },
    });

    const mimeType = this.pickMime();
    this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });
    this.chunks = [];

    this.mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) {
        this.chunks.push(ev.data);
      }
    };

    this.mediaRecorder.onstop = () => {
      const durationMs = Math.max(0, performance.now() - this.startedAt);
      const blob = new Blob(this.chunks, { type: mimeType });
      this.stream?.getTracks().forEach((t) => t.stop());
      this.stream = null;
      this.mediaRecorder = null;
      this.resolveStop?.({ blob, durationMs: Math.round(durationMs), mimeType });
      this.resolveStop = null;
      this.rejectStop = null;
    };

    this.mediaRecorder.onerror = (ev) => {
      const err = (ev as ErrorEvent).error ?? new Error("MediaRecorder error");
      this.rejectStop?.(err);
      this.resolveStop = null;
      this.rejectStop = null;
    };

    this.startedAt = performance.now();
    this.mediaRecorder.start();
  }

  stop(): Promise<RecordingResult> {
    if (!this.mediaRecorder) {
      return Promise.reject(new Error("recorder not started"));
    }
    return new Promise<RecordingResult>((resolve, reject) => {
      this.resolveStop = resolve;
      this.rejectStop = reject;
      this.mediaRecorder?.stop();
    });
  }

  abort(): void {
    if (!this.mediaRecorder) return;
    this.mediaRecorder.onstop = null;
    this.mediaRecorder.stop();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.mediaRecorder = null;
    this.stream = null;
    this.resolveStop = null;
    this.rejectStop = null;
  }

  get isRecording(): boolean {
    return this.mediaRecorder?.state === "recording";
  }
}
