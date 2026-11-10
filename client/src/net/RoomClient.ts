import type {
  ClientMessage, DuelMessage, Hand, Member, PetMotion, ProfilePatch, RoomInfo, ServerMessage, StateUpdate,
} from "./protocol";
import { toWsUrl } from "./protocol";

export type ConnState = "idle" | "connecting" | "open" | "reconnecting";

export interface RoomEvents {
  onConnState(state: ConnState): void;
  onJoined(room: string, you: string, members: Member[]): void;
  /** Right after `onJoined` (null from servers without room info), and on every `room_info`. */
  onRoomInfo(info: RoomInfo | null): void;
  onMemberJoined(member: Member): void;
  onMemberLeft(id: string): void;
  onTap(id: string, count: number, total: number): void;
  onMotion(id: string, pose: PetMotion): void;
  onEmote(id: string, emote: string): void;
  onScratch(id: string, shards: number): void;
  onState(update: StateUpdate): void;
  /** Rock-paper-scissors: invites, rounds and endings of the own duels, and every result in the room. */
  onDuel(msg: DuelMessage): void;
  /** A member wears an emote as a sticker for `sec` seconds. */
  onSticker(id: string, key: string, sec: number): void;
  /** A final room_full carries its reason as the code: kicked, banned or need_save. */
  onError(code: string, message: string): void;
}

export interface JoinInfo {
  room: string;
  nick: string;
  character: string;
  /** Secret guest-save token (stable uid, plate check); never shown to others. */
  token?: string;
  /** Main-site account token; the room uses the save linked to the account. */
  accountToken?: string;
  /** Name plate (a big hidden card id or a manifest `plates` id); the server drops it unless the save has unlocked it. */
  plate?: string;
  /** Turns rock-paper-scissors invites down; kept for every rejoin. */
  dnd?: boolean;
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
  /** `join` was sent on this socket and `joined` has not arrived yet. */
  private joinPending = false;
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
  sendSetPublic(isPublic: boolean): void {
    this.send({ type: "set_public", public: isPublic });
  }
  sendKick(id: string): void {
    this.send({ type: "kick", id });
  }
  /** Do-not-disturb for the next joins; [tell] also sends it now, only to servers with duels (older ones answer an
   * unknown type with bad_message). */
  setDnd(on: boolean, tell: boolean): void {
    if (this.joinInfo) this.joinInfo.dnd = on || undefined;
    if (tell) this.send({ type: "dnd", dnd: on });
  }
  sendDuelInvite(id: string, bet: number): void {
    this.send({ type: "duel_invite", id, bet });
  }
  sendDuelAnswer(duel: string, accept: boolean): void {
    this.send({ type: "duel_answer", duel, accept });
  }
  sendDuelThrow(duel: string, hand: Hand): void {
    this.send({ type: "duel_throw", duel, hand });
  }
  sendState(patch: ProfilePatch): void {
    if (this.joinInfo) {
      if (patch.character) this.joinInfo.character = patch.character;
      if (patch.nick) this.joinInfo.nick = patch.nick;
      if (patch.plate !== undefined) this.joinInfo.plate = patch.plate || undefined;
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
      if (this.joinInfo) {
        this.send({ type: "join", ...this.joinInfo });
        this.joinPending = true;
      }
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
      this.joinPending = false;
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
        this.joinPending = false;
        this.events.onJoined(msg.room, msg.you, msg.members);
        this.events.onRoomInfo(msg.info ? { ...msg.info } : null);
        break;
      case "room_info": {
        const { type: _, ...info } = msg;
        this.events.onRoomInfo(info);
        break;
      }
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
      case "motion_batch":
        for (const { id, ...pose } of msg.motions) this.events.onMotion(id, pose);
        break;
      case "emote":
        this.events.onEmote(msg.id, msg.emote);
        break;
      case "scratch":
        this.events.onScratch(msg.id, msg.shards);
        break;
      case "state":
        this.events.onState(msg);
        break;
      case "duel_invite":
      case "duel_start":
      case "duel_round":
      case "duel_result":
      case "duel_over":
        this.events.onDuel(msg);
        break;
      case "sticker":
        this.events.onSticker(msg.id, msg.key, msg.sec);
        break;
      case "error":
        // A full room, or a join the server rejected as invalid, is permanent for this attempt: stop retrying.
        // Being removed by the host or refused by a public room also comes as room_full, with a reason.
        if (msg.code === "room_full" || (msg.code === "bad_message" && this.joinPending)) this.stop(true);
        this.events.onError(msg.code === "room_full" && msg.reason ? msg.reason : msg.code, msg.message);
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
        // No pong since last ping: the connection is dead. Its close handshake can take a minute,
        // so drop the socket now (its late onclose is ignored) and reconnect right away.
        const dead = this.ws;
        this.ws = null;
        this.joinPending = false;
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
      this.send({ type: "ping" });
    }, this.opts.pingMs);
  }

  private stopPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private stop(emit: boolean): void {
    this.wantOpen = false;
    this.joinPending = false;
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
