// Wire types — keep in sync with ../../../protocol/PROTOCOL.md and server/app/models.py.
// Input sharing carries tap counts and bounded pet animation offsets.

export interface PetMotion {
  dx: number;
  dy: number;
  keyDown: boolean;
  left: boolean;
  right: boolean;
}

export const restingMotion = (): PetMotion => ({ dx: 0, dy: 0, keyDown: false, left: false, right: false });

/**
 * The newest room motion format this client reads: 2 packed deltas for subscribed members, 3 the same with each
 * room's button edges gathered into one ordered `motion_edges` message.
 */
export const MOTION_VERSION = 3;

/** Quarter-pixel coordinates and keyboard/left/right bits. Absent fields retain their last value. */
export interface PackedMotion { x: number; y: number; b: number }
export type MotionDelta = Partial<PackedMotion> & { id: string };
export const packMotion = (p: PetMotion): PackedMotion => ({
  x: Math.round(p.dx * 4), y: Math.round(p.dy * 4), b: Number(p.keyDown) | Number(p.left) << 1 | Number(p.right) << 2,
});
export const unpackMotion = (p: PackedMotion): PetMotion => ({
  dx: p.x / 4, dy: p.y / 4, keyDown: !!(p.b & 1), left: !!(p.b & 2), right: !!(p.b & 4),
});

export interface Member {
  id: string;
  /** Stable per room for players with a token (null otherwise); used to remember desk positions. */
  uid?: string | null;
  nick: string;
  character: string;
  taps: number;
  motion?: PetMotion | null;
  /** Name plate worn: a big hidden card id or a manifest `plates` id, checked by the server (null = none). */
  plate?: string | null;
}

/** Profile fields a member can change with `state` ("" takes off the plate). */
export interface ProfilePatch {
  character?: string;
  nick?: string;
  plate?: string;
}

export interface StateUpdate {
  type: "state";
  id: string;
  character: string;
  nick: string;
  plate?: string | null;
}

/** Room-wide state from `joined` and `room_info`; servers before 1.2 send none. */
export interface RoomInfo {
  /** Member id of the host, who can list the room and remove members. */
  host: string | null;
  public: boolean;
}

/** One entry of `GET /rooms`. */
export interface PublicRoom {
  room: string;
  host: { nick: string; character: string };
  members: number;
  max: number;
}

export type Hand = "rock" | "paper" | "scissors";
export const HANDS: readonly Hand[] = ["rock", "scissors", "paper"];

/** Rock-paper-scissors messages from the server; only the two members of a duel hear all but `duel_result`. */
export type DuelMessage =
  /** To both sides: [from] invited [to]; the answer is due in `sec` seconds. */
  | { type: "duel_invite"; duel: string; from: string; to: string; bet: number; prize: number; sec: number }
  /** To both sides: the bets are taken, round 1 is due in `sec` seconds. */
  | { type: "duel_start"; duel: string; round: number; sec: number }
  /** To both sides after a draw: its hands by member id, and the next round. */
  | { type: "duel_round"; duel: string; round: number; sec: number; hands: Record<string, Hand> }
  /** To the whole room: the winner got `prize` shards; hands by member id, null for none thrown. */
  | { type: "duel_result"; duel: string; winner: string; loser: string; prize: number; hands: Record<string, Hand | null> }
  /** To both sides: ended without a winner (declined, timeout, gone, no_shards, duel_cap; idle and draws refund). */
  | { type: "duel_over"; duel: string; reason: string };

export type ClientMessage =
  | {
    type: "join"; room: string; nick: string; character: string; token?: string; accountToken?: string; plate?: string;
    /** Turns rock-paper-scissors invites down; servers without duels ignore it. */
    dnd?: boolean;
    motionVersion?: number;
  }
  | { type: "leave" }
  | { type: "tap"; count: number }
  | ({ type: "motion" } & PetMotion)
  | ({ type: "pose" } & Partial<PackedMotion>)
  | { type: "motion_subscribe"; ids: string[] }
  /** Only to servers that list "poke" in `joined.features`. */
  | { type: "poke"; id: string }
  /** Only to servers that list "profile" in `joined.features`. */
  | { type: "profile"; id: string }
  | { type: "emote"; emote: string }
  | ({ type: "state" } & ProfilePatch)
  | { type: "ping" }
  | { type: "set_public"; public: boolean }
  | { type: "kick"; id: string }
  | { type: "dnd"; dnd: boolean }
  | { type: "duel_invite"; id: string; bet: number }
  | { type: "duel_answer"; duel: string; accept: boolean }
  | { type: "duel_throw"; duel: string; hand: Hand };

export type ServerMessage =
  | {
    type: "joined"; room: string; you: string; members: Member[]; info?: RoomInfo; motionVersion?: number;
    /** Room messages this server takes beyond the 1.1 set, e.g. "poke"; missing on older servers. */
    features?: string[];
    /** The room's cheer bar as it stands, from servers with cheer rounds. */
    cheer?: CheerState;
  }
  | ({ type: "room_info" } & RoomInfo)
  | { type: "member_joined"; member: Member }
  | { type: "member_left"; id: string }
  | { type: "tap"; id: string; count: number; total: number }
  | ({ type: "motion"; id: string } & PetMotion)
  | { type: "motion_batch"; motions: ({ id: string } & PetMotion)[] }
  | { type: "motion_delta" | "motion_snapshot"; motions: MotionDelta[] }
  | ({ type: "motion_edge" } & MotionDelta)
  /** Button edges of the last 50ms, oldest first; one member may appear more than once. */
  | { type: "motion_edges"; edges: MotionDelta[] }
  | { type: "emote"; id: string; emote: string }
  /** [from] poked [to]; `quiet` on the copy for a member poked while turning invites down. */
  | { type: "poke"; from: string; to: string; quiet?: boolean }
  /** A member's scratch card paid enough shards to tell the room. */
  | { type: "scratch"; id: string; shards: number }
  /** To the member who asked: member [id]'s profile. */
  | ({ type: "profile"; id: string } & MemberProfile)
  /** The room's cheer bar: at most every 2 s while it fills, after a round, and on joining while one is under way. */
  | ({ type: "cheer" } & CheerState)
  /** Cheer round [round] finished: the shards each paid member got (0 once that save's cheer for the day is used up). */
  | { type: "cheer_done"; round: number; rewards: Record<string, number> }
  | StateUpdate
  | DuelMessage
  /** A member wears emote [key] for `sec` more seconds: a duel's loser. */
  /** reason: why a room_full ends the session (kicked | banned | need_save). */
  | { type: "error"; code: string; message: string; reason?: string }
  | { type: "pong" };

/**
 * A room's cheer bar: members' paid taps toward `target` this round (a member who left keeps theirs in `total`), each
 * present member's share by member id, the share from which a save cheers, how many cheer (`target` grows with them),
 * the shards each of them gets when the bar is full, and the rounds the room has finished.
 */
export interface CheerState {
  target: number; minShare: number; total: number; shares: Record<string, number>; count: number; reward: number; rounds: number;
}

/** [owned, total] of each kind, counted as the album does. */
export interface CollectionProgress { cards: [number, number]; emotes: [number, number]; skins: [number, number] }
/** What a member's profile shows of its save: up to three showcase card ids, and progress (null without a save). */
export interface MemberProfile { showcase: string[]; progress: CollectionProgress | null }

export const MAX_ROOM_SIZE = 20;
/** Cards a save may pin to its profile. */
export const MAX_SHOWCASE = 3;
/** Longest nick the boards keep; the same as game.py MAX_BOARD_NICK. */
export const MAX_BOARD_NICK = 24;

/** http(s)://host[:port][/base] -> ws(s)://host[:port][/base]/ws */
export function toWsUrl(serverUrl: string): string {
  const u = new URL(serverUrl.trim());
  u.protocol = u.protocol === "https:" ? "wss:" : u.protocol === "http:" ? "ws:" : u.protocol;
  u.pathname = u.pathname.replace(/\/+$/, "") + "/ws";
  u.search = "";
  u.hash = "";
  return u.toString();
}

/** Base HTTP URL without trailing slash. */
export function toHttpBase(serverUrl: string): string {
  return serverUrl.trim().replace(/\/+$/, "");
}
