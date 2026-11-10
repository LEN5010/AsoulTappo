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
  }
  | { type: "leave" }
  | { type: "tap"; count: number }
  | ({ type: "motion" } & PetMotion)
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
  | { type: "joined"; room: string; you: string; members: Member[]; info?: RoomInfo }
  | ({ type: "room_info" } & RoomInfo)
  | { type: "member_joined"; member: Member }
  | { type: "member_left"; id: string }
  | { type: "tap"; id: string; count: number; total: number }
  | ({ type: "motion"; id: string } & PetMotion)
  | { type: "motion_batch"; motions: ({ id: string } & PetMotion)[] }
  | { type: "emote"; id: string; emote: string }
  /** A member's scratch card paid enough shards to tell the room. */
  | { type: "scratch"; id: string; shards: number }
  | StateUpdate
  | DuelMessage
  /** A member wears emote [key] for `sec` more seconds: a duel's loser. */
  | { type: "sticker"; id: string; key: string; sec: number }
  /** reason: why a room_full ends the session (kicked | banned | need_save). */
  | { type: "error"; code: string; message: string; reason?: string }
  | { type: "pong" };

export const MAX_ROOM_SIZE = 20;

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
