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
  /** A `ROOM_STATUSES` id (roomStatus.ts), null for none; servers before it send none. */
  status?: string | null;
  /** The member's client plays dou dizhu and the server has it; servers before it send none. */
  ddz?: boolean;
  /** The member's client queues for dou dizhu and opens tables; servers before it send none. */
  ddzMatch?: boolean;
}

/** Profile fields a member can change with `state` ("" takes off the plate). */
export interface ProfilePatch {
  character?: string;
  nick?: string;
  plate?: string;
  /** "" shows none. Servers before it ignore it and need one of the other fields in the same state. */
  status?: string;
}

export interface StateUpdate {
  type: "state";
  id: string;
  character: string;
  nick: string;
  plate?: string | null;
  status?: string | null;
}

/** Room-wide state from `joined` and `room_info`; servers before 1.2 send none. */
export interface RoomInfo {
  /** Member id of the host, who can list the room and remove members. */
  host: string | null;
  public: boolean;
  /** The name the host gave the room, blocked words masked; "" or missing for none (servers before names). */
  name?: string;
}

/** One entry of `GET /rooms`. */
export interface PublicRoom {
  room: string;
  /** "" or missing for none. */
  name?: string;
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

/**
 * A seat of a dou dizhu table as dealt: `away` while its member is out of the room, `auto` while it is played for;
 * `plate` the name plate its member wears, when one is.
 */
export interface DdzSeatInfo { id: string; nick: string; character: string; plate?: string | null; auto: boolean; away: boolean }

/** A seat of an open table: its member, one offered to a save of the queue (who stays unsaid), or null for empty. */
export type DdzOpenSeat = { id: string; nick: string; character: string } | { pending: true } | null;
/** An open table of the room, as `ddz_tables` lists it. */
export interface DdzOpenTable { table: string; base: number; seats: DdzOpenSeat[] }

/**
 * Dou dizhu messages from the server (server/app/ddz.py); all but `ddz_live` go to the three seats only. Seats are
 * numbered 0 to 2 in turn order; cards are 0..53 (src/ddz/rules.ts).
 */
export type DdzMessage =
  /**
   * Member [from] invited the two others of `ids` at base stake `base`; each seat pays `deposit` when all accept. A
   * table the queue made has no `from`, all three answer, and `seats` names its members, who may be in other rooms.
   * The seat of an open table offered to this save from the queue comes the same way, with `accepted` the seats taken
   * and an empty seat as "" in `ids` and null in `seats`.
   */
  | {
    type: "ddz_invite"; table: string; from?: string; ids: string[]; base: number; deposit: number; sec: number;
    match?: boolean; seats?: ({ id: string; nick: string; character: string; plate?: string | null } | null)[]; accepted?: string[];
  }
  /**
   * The open table this save sits at, whenever it changes: `you` is the own seat, `sec` the time until it is put away;
   * `starting` while the three deposits are taken (the deal, or the table waiting again, follows).
   */
  | {
    type: "ddz_open"; table: string; base: number; deposit: number; you: number; seats: DdzOpenSeat[]; sec: number;
    starting?: boolean;
  }
  /** The open tables of the room, oldest first; an empty list once the last goes. */
  | { type: "ddz_tables"; tables: DdzOpenTable[] }
  /** The opener of an open table calls this member to it; shown for `sec` seconds. */
  | { type: "ddz_call"; table: string; from: string; base: number; deposit: number; sec: number; seats: DdzOpenSeat[] }
  | { type: "ddz_answer"; table: string; id: string }
  /**
   * Ended with nothing won (declined, timeout, gone, nobid, no_shards, ddz_cap, ddz_locked, ddz_account: a seat's save
   * is not linked to a main-site account, error); deposits went back.
   */
  | { type: "ddz_over"; table: string; reason: string; by?: string }
  /** A deal: the own hand, and the seat that bids first once the cards are dealt out (`dealSec`). */
  | {
    type: "ddz_deal"; table: string; seats: DdzSeatInfo[]; you: number; hand: number[]; base: number; cap: number; deal: number;
    turn: number; sec: number; dealSec?: number;
    /** The own seat's card counter where it is sold: on for this game, and the games of it the save has left. */
    counter?: DdzCounter;
    watch?: undefined;
  }
  /**
   * A deal of the table this client watches: the viewed seat's hand (null when it is not shown), no own seat and no
   * counter.
   */
  | {
    type: "ddz_deal"; table: string; seats: DdzSeatInfo[]; hand: number[] | null; base: number; cap: number; deal: number;
    turn: number; sec: number; dealSec?: number; watch: true;
  }
  /** A bid (0 passes); `turn` bids next while the bidding goes on. */
  | { type: "ddz_bid"; table: string; seat: number; bid: number; turn?: number; sec?: number; watch?: true }
  | {
    type: "ddz_landlord"; table: string; seat: number; bid: number; bottom: number[]; mult: number; turn: number; sec: number;
    watch?: true;
  }
  /** A play ([] passes); `turn` plays next, and leads when `lead`. */
  | {
    type: "ddz_play"; table: string; seat: number; cards: number[]; left: number; mult: number; bombs: number;
    turn?: number; sec?: number; lead?: boolean; watch?: true;
  }
  /**
   * A seat's member left or came back, or its autopilot changed; with `turn` its turn starts over. A member back on a
   * connection with another nick, pet or plate brings them along.
   */
  | {
    type: "ddz_seat"; table: string; seat: number; id: string; away: boolean; auto: boolean; turn?: number; sec?: number;
    nick?: string; character?: string; plate?: string | null; watch?: true;
  }
  /** Seat `seat` of the own table showed emote `emote`, in whatever room. */
  | { type: "ddz_emote"; table: string; seat: number; emote: string; watch?: true }
  | {
    type: "ddz_result"; table: string; winner: "landlord" | "farmers"; landlord: number; bid: number; bombs: number;
    /** 0 none, 1 spring, 2 counter-spring. */
    spring: number; mult: number; base: number; deltas: number[]; hands: number[][]; sec: number; watch?: true;
  }
  | { type: "ddz_again"; table: string; seat: number; watch?: true }
  | { type: "ddz_closed"; table: string }
  /** The whole game, for a seat whose member came back. */
  | {
    type: "ddz_state"; table: string; phase: "bid" | "play"; you: number; hand: number[];
    seats: (DdzSeatInfo & { left: number; bid: number | null })[]; base: number; cap: number; deal: number; bid: number;
    landlord: number | null; bottom: number[]; mult: number; bombs: number; turn: number; lead: boolean;
    trick: (number[] | null)[]; sec: number; of: number;
    /** Every card played this deal, in order; left out by servers before the card counter. */
    played?: number[];
    counter?: DdzCounter;
  }
  /** The own seat's card counter now: the answer to asking for it, and sent when a game of it is used. */
  | { type: "ddz_counter"; table: string; on: boolean; left: number; error?: string }
  /**
   * To the whole room: the three members started (on) or ended a game; `gains` are the winners' shards by member id. A
   * room none of them is in by the end hears only that it ended.
   */
  | { type: "ddz_live"; table: string; ids: string[]; on: true; base?: number }
  | { type: "ddz_live"; table: string; ids?: string[]; on: false; gains?: Record<string, number> }
  /**
   * The queue, to clients that said `ddzMatch`: this connection waits at stake `base`, `waited` seconds so far; `base`
   * null when it does not, with `reason` when the server took it out (ddz_locked, ddz_account, no_shards, ddz_cap,
   * ddz_dnd, error), or ddz_match_cooldown with `retry`: the save declined a table of the queue or let it lapse, and
   * may queue again in that many seconds.
   */
  | { type: "ddz_queue"; base: number | null; waited?: number; reason?: string; retry?: number }
  /** How many saves wait at each stake, as [base, saves]; stakes nobody waits at are left out. */
  | { type: "ddz_waiting"; counts: [number, number][] }
  /**
   * The table this client watches, as seen from seat `seat`: the answer to each `ddz_watch`, a change of seat
   * included. `hand` is that seat's hand (null when it is not shown); `phase` is the server's own; `result` the last
   * `ddz_result` while the phase is "over".
   */
  | {
    type: "ddz_watch"; table: string; seat: number; hand: number[] | null; phase: "bid" | "play" | "settling" | "over";
    seats: (DdzSeatInfo & { left: number; bid: number | null; again?: boolean })[]; base: number; cap: number; deal: number;
    bid: number; landlord: number | null; bottom: number[]; mult: number; bombs: number; turn: number | null; lead: boolean;
    trick: (number[] | null)[]; sec: number; of: number; result: (DdzMessage & { type: "ddz_result" }) | null;
  }
  /**
   * Watching table `table` ended: it closed, it opened again for seats after a game (reopen), its game ended with
   * nothing won (gone, with `over` the reason ddz_over gives), or the own save started a game (playing). Not sent when
   * the watcher stopped or left.
   */
  | { type: "ddz_watch_end"; table: string; reason: "closed" | "reopen" | "gone" | "playing"; over?: string }
  /**
   * Who watches table `table`, to its seats and its watchers: each one's nick, pet and the seat whose hand it sees
   * (null for none). To a watcher, `you` is its own place in `faces`.
   */
  | { type: "ddz_watchers"; table: string; faces: DdzWatchFace[]; you?: number };

/** A watcher of a dou dizhu table, as `ddz_watchers` lists it. */
export interface DdzWatchFace { nick: string; character: string; seat: number | null }

/** A seat's card counter where the economy sells it (`doudizhu.counter`). */
export interface DdzCounter { on: boolean; left: number }

/** Dou dizhu messages to the server; only to servers whose economy has `doudizhu`. */
export type DdzClientMessage =
  | { type: "ddz_invite"; ids: string[]; base: number }
  | { type: "ddz_answer"; table: string; accept: boolean }
  | { type: "ddz_bid"; table: string; bid: number }
  | { type: "ddz_play"; table: string; cards: number[] }
  | { type: "ddz_auto"; table: string; on: boolean }
  /** Turn the own seat's card counter on, buying its games when the save has none left; where it is sold only. */
  | { type: "ddz_counter"; table: string }
  | { type: "ddz_again"; table: string }
  | { type: "ddz_leave"; table: string }
  /** Wait for a table at stake `base`, 0 to stop; only to servers that list "ddz_match" in `joined.features`. */
  | { type: "ddz_queue"; base: number }
  /** Open tables, to the same servers: open one at `base`, sit down at one (at `seat` when empty), call a member. */
  | { type: "ddz_open"; base: number }
  | { type: "ddz_sit"; table: string; seat?: number }
  | { type: "ddz_call"; table: string; id: string }
  /** An emote to the other seats of the own table. */
  | { type: "ddz_emote"; table: string; emote: string }
  /**
   * Watch table `table` from seat `seat` (0 when left out), or another seat of it; "" stops. Only on the room
   * connection, to servers that list "ddz_watch" in `joined.features`.
   */
  | { type: "ddz_watch"; table: string; seat?: number };

/** Who a dou dizhu connection is: the same as a room join's. */
export interface DdzHello {
  nick: string; character: string; token?: string; accountToken?: string; plate?: string; dnd?: boolean;
  /** This client knows watchers (`ddz_watchers`); servers without them ignore it. */
  ddzWatch?: boolean;
}

/** What a dou dizhu connection hears beyond the table's messages. */
export type DdzLinkMessage =
  | DdzMessage
  /**
   * The hello went through: its member id; the stake the save waits at, taken over from an older connection (null
   * when it does not); the table whose seat it took back (null for none: whatever it held before is gone).
   */
  | { type: "ddz_ready"; you: string; base: number | null; waited?: number; table: string | null }
  | { type: "error"; code: string; message: string; reason?: string }
  | { type: "pong" };

/** GET /api/ddz/lobby: what the lobby shows the save. */
export interface DdzLobby {
  /** The stakes: the deposit, whether the save can pay it, how many saves wait there (it included). */
  tiers: { base: number; deposit: number; afford: boolean; waiting: number }[];
  /** Today's net win, the cap and what is left under it. */
  net: number; cap: number; left: number;
  /** The taps the save has and needs. */
  taps: number; minTaps: number;
  /** Whether the save meets the account rule of the server. */
  account: boolean;
  /** The save holds a seat a dou dizhu connection takes back. */
  seated: boolean;
}

export type ClientMessage =
  | {
    type: "join"; room: string; nick: string; character: string; token?: string; accountToken?: string; plate?: string;
    /** Turns rock-paper-scissors invites down; servers without duels ignore it. */
    dnd?: boolean;
    /** A `ROOM_STATUSES` id to show the room; servers before it ignore it. */
    status?: string;
    /** This client plays dou dizhu; servers without it ignore it. */
    ddz?: boolean;
    /** This client also queues for dou dizhu tables across rooms; servers without the queue ignore it. */
    ddzMatch?: boolean;
    /** This client watches dou dizhu tables and knows watchers; servers without watching ignore it. */
    ddzWatch?: boolean;
    motionVersion?: number;
  }
  | { type: "leave" }
  | { type: "tap"; count: number }
  | ({ type: "motion" } & PetMotion)
  | ({ type: "pose" } & Partial<PackedMotion>)
  | { type: "motion_subscribe"; ids: string[] }
  /** Only to servers that list "poke" in `joined.features`. */
  | { type: "poke"; id: string }
  /** Drank water after a reminder; only to servers that list "drink". */
  | { type: "drink" }
  /** Only to servers that list "profile" in `joined.features`. */
  /** `showcase`: how many showcase cards this client lays out; servers before 1.2.5 ignore it and send three. */
  | { type: "profile"; id: string; showcase?: number }
  | { type: "emote"; emote: string }
  | ({ type: "state" } & ProfilePatch)
  | { type: "ping" }
  | { type: "set_public"; public: boolean }
  /** Host only; only to servers that list "name". */
  | { type: "set_name"; name: string }
  | { type: "kick"; id: string }
  | { type: "dnd"; dnd: boolean }
  | { type: "duel_invite"; id: string; bet: number }
  | { type: "duel_answer"; duel: string; accept: boolean }
  | { type: "duel_throw"; duel: string; hand: Hand }
  /** Opens a dou dizhu connection, in no room. */
  | ({ type: "ddz_hello" } & DdzHello)
  | DdzClientMessage;

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
  /** Member [id] drank water after a reminder; not sent back to that member. */
  | { type: "drink"; id: string }
  /** A member's scratch card paid enough shards to tell the room. */
  | { type: "scratch"; id: string; shards: number }
  /** A member won at least economy.park.race.roomAt shards in one dumpling race. */
  | { type: "race_win"; id: string; coins: number }
  /** To the member who asked: member [id]'s profile. */
  | ({ type: "profile"; id: string } & MemberProfile)
  /** The room's cheer bar: at most every 2 s while it fills, after a round, and on joining while one is under way. */
  | ({ type: "cheer" } & CheerState)
  /** Cheer round [round] finished: the shards each paid member got (0 once that save's cheer for the day is used up). */
  | { type: "cheer_done"; round: number; rewards: Record<string, number> }
  | StateUpdate
  | DuelMessage
  | DdzMessage
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
/** What a member's profile shows of its save: up to MAX_SHOWCASE showcase card ids, and progress (null without a save). */
export interface MemberProfile { showcase: string[]; progress: CollectionProgress | null }

export const MAX_ROOM_SIZE = 20;
/** Characters of a room name, as the server cuts it (rooms.ROOM_NAME_MAX). */
export const ROOM_NAME_MAX = 16;
/** Cards a save may pin to its profile. */
export const MAX_SHOWCASE = 5;
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
