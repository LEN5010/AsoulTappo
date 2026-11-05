import type { ClientMessage, Member, PetMotion, ProfilePatch, ServerMessage, StateUpdate } from "./protocol";
import { toWsUrl } from "./protocol";

export type ConnState = "idle" | "connecting" | "open" | "reconnecting";

export interface RoomEvents {
  onConnState(state: ConnState): void;
  onJoined(room: string, you: string, members: Member[]): void;
  onMemberJoined(member: Member): void;
  onMemberLeft(id: string): void;
  onTap(id: string, count: number, total: number): void;
  onMotion(id: string, pose: PetMotion): void;
  onEmote(id: string, emote: string): void;
  onState(update: StateUpdate): void;
  onError(code: string, message: string): void;
}

export interface JoinInfo {
  room: string;
  nick: string;
  character: string;
  /** Secret player token (enables frame/badge); never shown to others. */
  token?: string;
}

/** Minimal WebSocket shape so tests can inject a fake. */
export interface WsLike {
  readyState: number;
  send(data: string): void;
  close(): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

export interface RoomClientOptions {
  createSocket?: (url: string) => WsLike;
  pingMs?: number;
  /** Backoff: min(maxDelay, base * 2^attempt) + jitter */
  baseDelayMs?: number;
  maxDelayMs?: number;
}

const OPEN = 1;

/**
 * WebSocket room client with keepalive pings and automatic reconnect
 * (exponential backoff). On every (re)connect it re-sends `join` for the
 * room it was last asked to join, until `leave()` is called.
 */
export class RoomClient {
  private ws: WsLike | null = null;
  private serverUrl = "";
  private joinInfo: JoinInfo | null = null;
  private wantOpen = false;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private gotPong = true;
  private readonly opts: Required<RoomClientOptions>;

  constructor(
    private readonly events: RoomEvents,
    opts: RoomClientOptions = {},
  ) {
    this.opts = {
      createSocket: opts.createSocket ?? ((url) => new WebSocket(url) as unknown as WsLike),
      pingMs: opts.pingMs ?? 20000,
      baseDelayMs: opts.baseDelayMs ?? 500,
      maxDelayMs: opts.maxDelayMs ?? 15000,
    };
  }

  /** Connect to `serverUrl` and join `info.room`. Replaces any previous session. */
  join(serverUrl: string, info: JoinInfo): void {
    this.stop(false);
    this.serverUrl = serverUrl;
    this.joinInfo = info;
    this.wantOpen = true;
    this.attempt = 0;
    this.open();
  }

  /** Leave the room and close the connection (no reconnect). */
  leave(): void {
    this.stop(true);
  }

  get connected(): boolean {
    return this.ws?.readyState === OPEN;
  }

  sendTap(count: number): void {
    this.send({ type: "tap", count });
  }
  sendMotion(pose: PetMotion): void {
    this.send({ type: "motion", ...pose });
  }
  sendEmote(emote: string): void {
    this.send({ type: "emote", emote });
  }
  sendState(patch: ProfilePatch): void {
    if (this.joinInfo) {
      if (patch.character) this.joinInfo.character = patch.character;
      if (patch.nick) this.joinInfo.nick = patch.nick;
    }
    this.send({ type: "state", ...patch });
  }

  private send(msg: ClientMessage): void {
    if (this.ws && this.ws.readyState === OPEN) this.ws.send(JSON.stringify(msg));
  }

  private open(): void {
    let url: string;
    try {
      url = toWsUrl(this.serverUrl);
    } catch {
      this.events.onError("bad_url", "服务器地址无效");
      this.wantOpen = false;
      this.events.onConnState("idle");
      return;
    }
    this.events.onConnState(this.attempt === 0 ? "connecting" : "reconnecting");
    let ws: WsLike;
    try {
      ws = this.opts.createSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.attempt = 0;
      this.gotPong = true;
      this.events.onConnState("open");
      if (this.joinInfo) this.send({ type: "join", ...this.joinInfo });
      this.startPing();
    };
    ws.onmessage = (ev) => {
      if (this.ws !== ws || typeof ev.data !== "string") return;
      let msg: ServerMessage;
      try {
        msg = JSON.parse(ev.data) as ServerMessage;
      } catch {
        return;
      }
      this.dispatch(msg);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.stopPing();
      if (this.wantOpen) this.scheduleReconnect();
      else this.events.onConnState("idle");
    };
    ws.onerror = () => {
      /* onclose follows */
    };
  }

  private dispatch(msg: ServerMessage): void {
    switch (msg.type) {
      case "joined":
        this.events.onJoined(msg.room, msg.you, msg.members);
        break;
      case "member_joined":
        this.events.onMemberJoined(msg.member);
        break;
      case "member_left":
        this.events.onMemberLeft(msg.id);
        break;
      case "tap":
        this.events.onTap(msg.id, msg.count, msg.total);
        break;
      case "motion": {
        const { type: _, id, ...pose } = msg;
        this.events.onMotion(id, pose);
        break;
      }
      case "emote":
        this.events.onEmote(msg.id, msg.emote);
        break;
      case "state":
        this.events.onState(msg);
        break;
      case "error":
        // A full room is permanent for this attempt: stop retrying.
        if (msg.code === "room_full") this.stop(true);
        this.events.onError(msg.code, msg.message);
        break;
      case "pong":
        this.gotPong = true;
        break;
    }
  }

  private scheduleReconnect(): void {
    if (!this.wantOpen || this.reconnectTimer) return;
    const { baseDelayMs, maxDelayMs } = this.opts;
    const delay = Math.min(maxDelayMs, baseDelayMs * 2 ** this.attempt) + Math.random() * 250;
    this.attempt += 1;
    this.events.onConnState("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.wantOpen) this.open();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (!this.gotPong) {
        // No pong since last ping: connection is dead, force a reconnect.
        this.ws?.close();
        return;
      }
      this.gotPong = false;
      this.send({ type: "ping" });
    }, this.opts.pingMs);
  }

  private stopPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private stop(emit: boolean): void {
    this.wantOpen = false;
    this.joinInfo = emit ? null : this.joinInfo;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.stopPing();
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      try {
        if (ws.readyState === OPEN) ws.send(JSON.stringify({ type: "leave" } satisfies ClientMessage));
        ws.close();
      } catch {
        /* ignore */
      }
    }
    if (emit) this.events.onConnState("idle");
  }
}
