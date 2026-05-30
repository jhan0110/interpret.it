import type {
  AudioSubmission,
  ClientMessage,
  ServerMessage,
  WSAudioAck,
  WSAudioSubmitHeader,
  WSError,
  WSGenerationComplete,
  WSGenerationProgress,
  WSMasteryUpdate,
  WSProsodyResult,
  WSRecordingBegin,
  WSSegmentPlay,
  WSSegmentRequest,
  WSSemanticResult,
  WSSessionComplete,
  WSSessionCompleteAck,
  WSSessionStart,
  WSStateChange,
} from "./contracts";

export type WSEventMap = {
  "segment.play": WSSegmentPlay["payload"];
  "audio.ack": WSAudioAck["payload"];
  "prosody.result": WSProsodyResult["payload"];
  "semantic.result": WSSemanticResult["payload"];
  "mastery.update": WSMasteryUpdate["payload"];
  "session.complete_ack": WSSessionCompleteAck["payload"];
  "state.change": WSStateChange["payload"];
  "generation.progress": WSGenerationProgress["payload"];
  "generation.complete": WSGenerationComplete["payload"];
  error: WSError["payload"];
  connected: void;
  disconnected: { code: number; reason: string };
};

type Handler<T> = (payload: T) => void;
type Handlers = {
  [K in keyof WSEventMap]?: Handler<WSEventMap[K]>[];
};

const BACKOFF_CAP_MS = 30_000;

export class WSClient {
  private ws: WebSocket | null = null;
  private handlers: Handlers = {};
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(
    private readonly url: string,
    private readonly token?: string
  ) {}

  connect(): void {
    this.closed = false;
    this._open();
  }

  private _open(): void {
    const fullUrl = this.token ? `${this.url}?token=${this.token}` : this.url;
    this.ws = new WebSocket(fullUrl);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      this._emit("connected", undefined as void);
    };

    this.ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        // Binary frames are Opus blobs — no client-side processing needed beyond forwarding
        return;
      }
      try {
        const msg = JSON.parse(ev.data as string) as ServerMessage;
        this._dispatch(msg);
      } catch (err) {
        // Malformed frame — log a short preview so envelope drift
        // doesn't disappear silently into the dev console.
        const preview = typeof ev.data === "string"
          ? ev.data.slice(0, 120)
          : "(non-string)";
        console.warn("[ws] dropped malformed frame:", preview, err);
      }
    };

    this.ws.onclose = (ev) => {
      this._emit("disconnected", { code: ev.code, reason: ev.reason });
      if (!this.closed) {
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose always follows onerror; reconnect handled there
    };
  }

  private _scheduleReconnect(): void {
    const delay = Math.min(
      BACKOFF_CAP_MS,
      1_000 * Math.pow(2, this.reconnectAttempt)
    );
    this.reconnectAttempt++;
    this.reconnectTimer = setTimeout(() => this._open(), delay);
  }

  private _dispatch(msg: ServerMessage): void {
    switch (msg.type) {
      case "segment.play":
        this._emit("segment.play", msg.payload);
        break;
      case "audio.ack":
        this._emit("audio.ack", msg.payload);
        break;
      case "prosody.result":
        this._emit("prosody.result", msg.payload);
        break;
      case "semantic.result":
        this._emit("semantic.result", msg.payload);
        break;
      case "mastery.update":
        this._emit("mastery.update", msg.payload);
        break;
      case "session.complete_ack":
        this._emit("session.complete_ack", msg.payload);
        break;
      case "state.change":
        this._emit("state.change", msg.payload);
        break;
      case "generation.progress":
        this._emit("generation.progress", msg.payload);
        break;
      case "generation.complete":
        this._emit("generation.complete", msg.payload);
        break;
      case "error":
        this._emit("error", msg.payload);
        break;
    }
  }

  on<K extends keyof WSEventMap>(event: K, handler: Handler<WSEventMap[K]>): () => void {
    if (!this.handlers[event]) {
      (this.handlers as Record<string, Handler<unknown>[]>)[event] = [];
    }
    (this.handlers[event] as Handler<WSEventMap[K]>[]).push(handler);
    return () => this.off(event, handler);
  }

  off<K extends keyof WSEventMap>(event: K, handler: Handler<WSEventMap[K]>): void {
    const list = this.handlers[event] as Handler<WSEventMap[K]>[] | undefined;
    if (!list) return;
    const idx = list.indexOf(handler);
    if (idx !== -1) list.splice(idx, 1);
  }

  private _emit<K extends keyof WSEventMap>(event: K, payload: WSEventMap[K]): void {
    const list = this.handlers[event] as Handler<WSEventMap[K]>[] | undefined;
    list?.forEach((h) => h(payload));
  }

  /** Send a JSON control envelope. */
  send(msg: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  /**
   * Submit audio: sends `audio.submit_header` JSON envelope FIRST,
   * then the binary Opus blob as the very next frame.
   */
  submitAudio(submission: AudioSubmission, blob: Blob): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    const header: WSAudioSubmitHeader = {
      type: "audio.submit_header",
      ts: new Date().toISOString(),
      payload: submission,
    };
    this.ws.send(JSON.stringify(header));
    this.ws.send(blob);
  }

  sendSessionStart(sessionId: string): void {
    const msg: WSSessionStart = {
      type: "session.start",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId },
    };
    this.send(msg);
  }

  sendSegmentRequest(sessionId: string): void {
    const msg: WSSegmentRequest = {
      type: "segment.request",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId },
    };
    this.send(msg);
  }

  sendRecordingBegin(sessionId: string, segmentId: string, attemptId: string): void {
    const msg: WSRecordingBegin = {
      type: "recording.begin",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId, segment_id: segmentId, attempt_id: attemptId },
    };
    this.send(msg);
  }

  sendSessionComplete(sessionId: string): void {
    const msg: WSSessionComplete = {
      type: "session.complete",
      ts: new Date().toISOString(),
      payload: { session_id: sessionId },
    };
    this.send(msg);
  }

  close(): void {
    this.closed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
  }

  get readyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }
}
