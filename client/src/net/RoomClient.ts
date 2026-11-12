import type {
  CheerState, ClientMessage, DuelMessage, Hand, Member, MemberProfile, MotionDelta, PackedMotion, PetMotion, ProfilePatch, RoomInfo, ServerMessage,
  StateUpdate,
} from "./protocol";
import { MOTION_VERSION, packMotion, unpackMotion, toWsUrl } from "./protocol";
import { APP_VERSION } from "../version";

export type ConnState = "idle" | "connecting" | "open" | "reconnecting";

export interface RoomEvents {
  onConnState(state: ConnState): void;
  onJoined(room: string, you: string, members: Member[], features: string[]): void;
  /** Right after `onJoined` (null from servers without room info), and on every `room_info`. */
  onRoomInfo(info: RoomInfo | null): void;
  onMemberJoined(member: Member): void;
  onMemberLeft(id: string): void;
  onTap(id: string, count: number, total: number): void;
  onMotion(id: string, pose: PetMotion): void;
  onEmote(id: string, emote: string): void;
  /** [from] poked [to]; [quiet] when the member poked turns invites down (no bubble then). */
  onPoke(from: string, to: string, quiet: boolean): void;
  /** The answer to `sendProfile`: member [id]'s profile. */
  onProfile(id: string, profile: MemberProfile): void;
  /** The room's cheer bar, and a round finished with each paid member's shards. */
  onCheer(state: CheerState): void;
  onCheerDone(round: number, rewards: Record<string, number>): void;
  onScratch(id: string, shards: number): void;
  onState(update: StateUpdate): void;
  /** Rock-paper-scissors: invites, rounds and endings of the own duels, and every result in the room. */
  onDuel(msg: DuelMessage): void;
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
  /** A `ROOM_STATUSES` id shown to the room. */
  status?: string;
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
  /**
   * The motion version asked for in `join`. The 1.1.4 server takes 1 and 2 only and refuses the whole join otherwise
   * (bad_message), so a refused join is sent again asking for 2; that server is then asked for 2 until `join()`.
   */
  private joinVersion = MOTION_VERSION;
  private motionV2 = false;
  private interest: string[] = [];
  /** The subscription the server holds, as JSON; a member who just joined is subscribed to nobody. */
  private sentInterest = "[]";
  private sentPose: PackedMotion | null = null;
  private poses = new Map<string, PackedMotion>();
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
    this.joinVersion = MOTION_VERSION;
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
  /** Packed motion names the fields that changed since the last pose sent; a pose that packs the same is not sent. */
  sendMotion(pose: PetMotion): void {
    if (!this.motionV2) { this.send({ type: "motion", ...pose }); return; }
    const packed = packMotion(pose);
    const patch: Partial<PackedMotion> = {};
    for (const key of ["x", "y", "b"] as const) if (packed[key] !== this.sentPose?.[key]) patch[key] = packed[key];
    if (!Object.keys(patch).length) return;
    this.sentPose = packed;
    this.send({ type: "pose", ...patch });
  }
  /** The members whose movement this client shows. Kept across reconnects; without packed motion the server sends everyone's. */
  subscribeMotion(ids: string[]): void {
    // The server takes a room's worth of ids at most (MAX_ROOM_SIZE).
    this.interest = [...new Set(ids)].sort().slice(0, 20);
    const key = JSON.stringify(this.interest);
    if (this.motionV2 && this.connected && key !== this.sentInterest) {
      this.send({ type: "motion_subscribe", ids: this.interest });
      this.sentInterest = key;
    }
  }
  private motionDelta({ id, ...patch }: MotionDelta): void {
    const pose = { ...(this.poses.get(id) ?? { x: 0, y: 0, b: 0 }), ...patch };
    this.poses.set(id, pose);
    this.events.onMotion(id, unpackMotion(pose));
  }
  sendPoke(id: string): void {
    this.send({ type: "poke", id });
  }
  sendProfile(id: string): void {
    this.send({ type: "profile", id });
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
      if (patch.status !== undefined) this.joinInfo.status = patch.status || undefined;
    }
    this.send({ type: "state", ...patch });
  }

  private send(msg: ClientMessage): void {
    if (this.ws && this.ws.readyState === OPEN) this.ws.send(JSON.stringify(msg));
  }

  private open(): void {
    this.motionV2 = false;
    this.sentPose = null;
    this.sentInterest = "[]";
    this.poses.clear();
    let url: string;
    try {
      url = `${toWsUrl(this.serverUrl)}?v=${encodeURIComponent(APP_VERSION)}`;
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
        this.send({ type: "join", ...this.joinInfo, motionVersion: this.joinVersion });
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
        // A server that knows packed motion says which version it speaks; every other one keeps hearing and
        // sending full poses. Version 3 only adds `motion_edges`, read below whatever was agreed.
        this.motionV2 = (msg.motionVersion ?? 1) >= 2;
        // A room joined again on the same connection starts from nothing, like the server's side of it.
        this.sentPose = null;
        this.sentInterest = "[]";
        this.poses.clear();
        for (const member of msg.members) if (member.motion) this.poses.set(member.id, packMotion(member.motion));
        this.events.onJoined(msg.room, msg.you, msg.members, msg.features ?? []);
        this.events.onRoomInfo(msg.info ? { ...msg.info } : null);
        if (msg.cheer) this.events.onCheer({ ...msg.cheer, shares: { ...msg.cheer.shares } });
        this.subscribeMotion(this.interest);
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
        this.poses.delete(msg.id);
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
      case "motion_edge":
        this.motionDelta(msg);
        break;
      case "motion_snapshot":
      case "motion_delta":
        for (const delta of msg.motions) this.motionDelta(delta);
        break;
      case "motion_edges":
        // In the order they happened: a press and its release in one batch are both shown (MotionFrames).
        for (const delta of msg.edges) this.motionDelta(delta);
        break;
      case "emote":
        this.events.onEmote(msg.id, msg.emote);
        break;
      case "poke":
        this.events.onPoke(msg.from, msg.to, !!msg.quiet);
        break;
      case "profile":
        this.events.onProfile(msg.id, { showcase: msg.showcase ?? [], progress: msg.progress ?? null });
        break;
      case "cheer":
        this.events.onCheer({
          target: msg.target, minShare: msg.minShare, total: msg.total, shares: { ...msg.shares }, count: msg.count,
          reward: msg.reward, rounds: msg.rounds,
        });
        break;
      case "cheer_done":
        this.events.onCheerDone(msg.round, { ...msg.rewards });
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
      case "error":
        if (msg.code === "bad_message" && this.joinPending && this.joinVersion > 2 && this.joinInfo) {
          this.joinVersion = 2;
          this.send({ type: "join", ...this.joinInfo, motionVersion: 2 });
          break;
        }
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
