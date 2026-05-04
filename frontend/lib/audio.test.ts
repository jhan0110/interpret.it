/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AttemptRecorder } from "./audio";

class FakeMediaStream {
  tracks: { stop: () => void }[] = [{ stop: vi.fn() }];
  getTracks() {
    return this.tracks;
  }
}

class FakeMediaRecorder {
  static isTypeSupported(mime: string) {
    return mime === "audio/webm;codecs=opus";
  }
  state: "inactive" | "recording" | "paused" = "inactive";
  ondataavailable: ((ev: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((ev: ErrorEvent) => void) | null = null;
  constructor(public stream: MediaStream, public opts: { mimeType: string }) {}
  start() {
    this.state = "recording";
    queueMicrotask(() => {
      this.ondataavailable?.({ data: new Blob(["x".repeat(128)], { type: this.opts.mimeType }) });
    });
  }
  stop() {
    this.state = "inactive";
    queueMicrotask(() => this.onstop?.());
  }
}

beforeEach(() => {
  // @ts-expect-error stub global
  globalThis.MediaRecorder = FakeMediaRecorder;
  // @ts-expect-error stub navigator
  globalThis.navigator.mediaDevices = {
    getUserMedia: vi.fn().mockResolvedValue(new FakeMediaStream()),
  };
});

describe("AttemptRecorder", () => {
  it("reports support when MediaRecorder accepts opus/webm", () => {
    expect(AttemptRecorder.isSupported()).toBe(true);
  });

  it("captures a single blob on start→stop", async () => {
    const r = new AttemptRecorder();
    await r.start();
    expect(r.isRecording).toBe(true);
    // Yield once so the queued ondataavailable fires
    await new Promise((resolve) => setTimeout(resolve, 0));
    const result = await r.stop();
    expect(result.blob.size).toBeGreaterThan(0);
    expect(result.mimeType).toContain("opus");
    expect(result.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("rejects stop() before start()", async () => {
    const r = new AttemptRecorder();
    await expect(r.stop()).rejects.toThrow(/not started/);
  });

  it("rejects double start", async () => {
    const r = new AttemptRecorder();
    await r.start();
    await expect(r.start()).rejects.toThrow(/already started/);
    await r.stop();
  });
});
