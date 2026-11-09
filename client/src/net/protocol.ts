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
  /** Big hidden card id worn as a name plate, checked by the server (null = none). */
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

export type ClientMessage =
  | { type: "join"; room: string; nick: string; character: string; token?: string; accountToken?: string; plate?: string }
  | { type: "leave" }
  | { type: "tap"; count: number }
  | ({ type: "motion" } & PetMotion)
  | { type: "emote"; emote: string }
  | ({ type: "state" } & ProfilePatch)
  | { type: "ping" };

export type ServerMessage =
  | { type: "joined"; room: string; you: string; members: Member[] }
  | { type: "member_joined"; member: Member }
  | { type: "member_left"; id: string }
  | { type: "tap"; id: string; count: number; total: number }
  | ({ type: "motion"; id: string } & PetMotion)
  | { type: "motion_batch"; motions: ({ id: string } & PetMotion)[] }
  | { type: "emote"; id: string; emote: string }
  | StateUpdate
  | { type: "error"; code: string; message: string }
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
