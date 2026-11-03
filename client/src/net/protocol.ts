// Wire types — keep in sync with ../../../protocol/PROTOCOL.md and server/app/models.py.
// Privacy: only tap COUNTS are ever sent; never key identities or mouse positions.

export interface Member {
  id: string;
  nick: string;
  character: string;
  taps: number;
}

export type ClientMessage =
  | { type: "join"; room: string; nick: string; character: string }
  | { type: "leave" }
  | { type: "tap"; count: number }
  | { type: "emote"; emote: string }
  | { type: "state"; character?: string; nick?: string }
  | { type: "ping" };

export type ServerMessage =
  | { type: "joined"; room: string; you: string; members: Member[] }
  | { type: "member_joined"; member: Member }
  | { type: "member_left"; id: string }
  | { type: "tap"; id: string; count: number; total: number }
  | { type: "emote"; id: string; emote: string }
  | { type: "state"; id: string; character: string; nick: string }
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
