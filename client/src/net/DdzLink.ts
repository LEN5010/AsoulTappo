import type { ClientMessage, DdzHello, DdzLinkMessage, DdzMessage } from "./protocol";
import { toWsUrl } from "./protocol";
import type { ConnState, WsLike } from "./RoomClient";
import { APP_VERSION } from "../version";

export interface DdzLinkEvents {
  onState(state: ConnState): void;
  /** The hello went through (on every connect): see `ddz_ready`. */
  onReady(you: string, base: number | null, waited: number, table: string | null): void;
  onDdz(msg: DdzMessage): void;
  /** A refusal; a final one (no_ddz, client_outdated, a hello the server does not know) stops the link first. */
  onError(code: string, message: string): void;
}

export interface DdzLinkOptions {
  createSocket?: (url: string) => WsLike;
  pingMs?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

const OPEN = 1;

/**
 * The dou dizhu connection: a second WebSocket to the server, in no room (server/app/ddz.py, ddz_hello). It says
 * hello on every (re)connect with the identity it was given, keeps alive with pings and reconnects with the room
 * client's backoff until `close()`.
 */
export class DdzLink {
  private ws: WsLike | null = null;
  private serverUrl = "";
  private hello: DdzHello | null = null;
  private wantOpen = false;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private gotPong = true;
  /** `ddz_hello` was sent on this socket and `ddz_ready` has not arrived yet. */
  private helloPending = false;
  private isReady = false;
  private readonly opts: Required<DdzLinkOptions>;

  constructor(private readonly events: DdzLinkEvents, opts: DdzLinkOptions = {}) {
    this.opts = {
      createSocket: opts.createSocket ?? ((url) => new WebSocket(url) as unknown as WsLike),
      pingMs: opts.pingMs ?? 20000,
      baseDelayMs: opts.baseDelayMs ?? 500,
      maxDelayMs: opts.maxDelayMs ?? 15000,
    };
  }

  /** Connects to `serverUrl` as [hello]; replaces any previous connection. */
  open(serverUrl: string, hello: DdzHello): void {
    this.stop(false);
    this.serverUrl = serverUrl;
    this.hello = hello;
    this.wantOpen = true;
    this.attempt = 0;
    this.connect();
  }

  /** Closes the connection for good (no reconnect). */
  close(): void {
    this.stop(true);
  }

  get active(): boolean {
    return this.wantOpen;
  }

  /** The hello went through on the current socket. */
  get ready(): boolean {
    return this.isReady && this.ws?.readyState === OPEN;
  }

  /** Changes what the next hello says, e.g. after `dnd` or `state` was sent. */
  patchHello(patch: Partial<DdzHello>): void {
    if (this.hello) this.hello = { ...this.hello, ...patch };
  }

  /** Sends once the hello went through; dropped otherwise. */
  send(msg: ClientMessage): void {
    if (this.ready) this.ws!.send(JSON.stringify(msg));
  }

  private connect(): void {
    let url: string;
    try {
      url = `${toWsUrl(this.serverUrl)}?v=${encodeURIComponent(APP_VERSION)}`;
    } catch {
      this.wantOpen = false;
      this.events.onError("bad_url", "服务器地址无效");
      this.events.onState("idle");
      return;
    }
    this.events.onState(this.attempt === 0 ? "connecting" : "reconnecting");
    let ws: WsLike;
    try {
      ws = this.opts.createSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    this.isReady = false;
    ws.onopen = () => {
      if (this.ws !== ws || !this.hello) return;
      this.attempt = 0;
      this.gotPong = true;
      ws.send(JSON.stringify({ type: "ddz_hello", ...this.hello } satisfies ClientMessage));
      this.helloPending = true;
      this.startPing();
    };
    ws.onmessage = (ev) => {
      if (this.ws !== ws || typeof ev.data !== "string") return;
      let msg: DdzLinkMessage;
      try {
        msg = JSON.parse(ev.data) as DdzLinkMessage;
      } catch {
        return;
      }
      this.dispatch(msg);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.isReady = this.helloPending = false;
      this.stopPing();
      if (this.wantOpen) this.scheduleReconnect();
      else this.events.onState("idle");
    };
    ws.onerror = () => {
      /* onclose follows */
    };
  }

  private dispatch(msg: DdzLinkMessage): void {
    switch (msg.type) {
      case "ddz_ready":
        this.helloPending = false;
        this.isReady = true;
        this.events.onState("open");
        this.events.onReady(msg.you, msg.base ?? null, msg.waited ?? 0, msg.table ?? null);
        return;
      case "pong":
        this.gotPong = true;
        return;
      case "error": {
        // A server without the game, an outdated client, or one that does not know the hello: nothing to retry.
        const final = msg.code === "no_ddz" || msg.code === "room_full" || (msg.code === "bad_message" && this.helloPending);
        if (final) this.stop(true);
        this.events.onError(msg.code === "room_full" && msg.reason ? msg.reason : msg.code, msg.message);
        return;
      }
      default:
        if (msg.type.startsWith("ddz_")) this.events.onDdz(msg);
    }
  }

  private scheduleReconnect(): void {
    if (!this.wantOpen || this.reconnectTimer) return;
    const { baseDelayMs, maxDelayMs } = this.opts;
    const delay = Math.min(maxDelayMs, baseDelayMs * 2 ** this.attempt) + Math.random() * 250;
    this.attempt += 1;
    this.events.onState("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.wantOpen) this.connect();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (!this.gotPong) {
        // No pong since the last ping: drop the socket now and reconnect (its late onclose is ignored).
        const dead = this.ws;
        this.ws = null;
        this.isReady = this.helloPending = false;
        this.stopPing();
        try {
          dead?.close();
        } catch {
          /* ignore */
        }
        this.scheduleReconnect();
        return;
      }
      this.gotPong = false;
      if (this.ws?.readyState === OPEN) this.ws.send(JSON.stringify({ type: "ping" } satisfies ClientMessage));
    }, this.opts.pingMs);
  }

  private stopPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private stop(emit: boolean): void {
    const was = this.wantOpen || !!this.ws;
    this.wantOpen = false;
    this.isReady = this.helloPending = false;
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
    if (emit && was) this.events.onState("idle");
  }
}
