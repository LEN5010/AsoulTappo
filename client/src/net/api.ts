// HTTP client for the progression API (see protocol/PROTOCOL.md). A guest save is identified by a random
// token kept in localStorage (the server only stores its hash); a linked save by a main-site account token.
import { APP_VERSION } from "../version";
import type { Rarity } from "../manifest";
import { MAX_SHOWCASE, type MemberProfile } from "./protocol";
import type { Economy } from "../stores/economy";

export interface PlayerStatus {
  player: string;
  shards: number;
  /**
   * Tap income: shards earned from taps today, the daily cap, today's shard-eligible taps and what the next tap
   * pays. Missing on servers before 1.1, which send only `multiplier` and `perMinute`.
   */
  income: { day?: string; today?: number; cap?: number; taps?: number; perTap?: number; multiplier: number; perMinute: number };
  /** All credited taps for the China calendar day; available from server 1.1.4. */
  dailyTaps?: { day: string; count: number };
  resonance: {
    pity: { legendary: number; skin: number }; hardPity: { legendary: number; skin: number }; total: number;
    /**
     * The save's draws from each limited pool that runs: how many, and how many since its last featured item.
     * `guaranteed` (server 1.2.6): the shared tiers whose next draw there gives a featured item.
     */
    banners?: Record<string, { pity: number; drawn: number; guaranteed?: Rarity[] }>;
  };
  totals: { taps: number; activeMinutes: number; owned: number; items: number };
  /** Missing on servers without daily check-in. */
  checkin?: { available: boolean };
  /** Seconds before taps count again after input too fast for a hand; missing on older servers. */
  tapCooldown?: number;
  /**
   * Seconds for which the server counts this save's input as automatic (an auto-clicker, a macro), 0 when it does
   * not; missing on older servers. Rooms do not show the save's taps and motion meanwhile.
   */
  autoInput?: number;
  /** Cooldowns the server gave the save today for going on after that; missing on servers before 1.2.5. */
  autoStrikes?: number;
  /** Scratch cards left today and cards since the last emote; missing on servers without them. */
  scratch?: { left: number; pity: number };
  /** Rock-paper-scissors: today's net win (prizes minus bets). Missing on servers without duels. */
  duel?: { net: number };
  /** Dou dizhu: today's net win. Missing on servers without the game. */
  ddz?: { net: number };
  /** Room cheer rounds: shards from them today, the daily cap, and the taps in all to take part. */
  cheer?: { day: string; got: number; cap: number; minTaps: number };
  /** Update rewards open on the server that this save has not claimed; missing on older servers. */
  updateRewards?: UpdateReward[];
  /** The park: coins held and the server-wide news of big wins. Missing on servers without a park. */
  park?: ParkStatus;
  credited?: number;
}
/** A big win somewhere on the server, told to every running pet once. Fields besides these depend on `kind`. */
export interface ParkNews {
  id: number;
  /** Server time in seconds. */
  ts: number;
  kind: string;
  nick: string;
  [detail: string]: unknown;
}
/** What every status carries on a server with a park: coins held, and the news of the last 15 minutes, oldest first. */
export interface ParkStatus { coins: number; news: ParkNews[]; /** Coins of today's free coin, only in the status that granted it. */ gifted?: number }
/** GET /api/park, and `park` in the answers of the park's own requests. */
export interface ParkState {
  coins: number;
  /** Taps in all reach economy.park.coin.minTaps. */
  unlocked: boolean;
  /** Today's free coin is still waiting. */
  gift: boolean;
  /** Stamps toward the next coin (0 to stampsPerCoin - 1), stamps in all, and badges earned (0 to 3). */
  stamps: number;
  stampsTotal: number;
  badge: number;
  /** Shards spent on coins today, and shards won in the park today. */
  today: { spent: number; won: number };
  /** The server-wide pool: the top prize of the next lottery draw. */
  jackpot: number;
}
/** Shards every save on `version` or newer can claim once. */
export interface UpdateReward {
  id: number;
  version: string;
  shards: number;
}
export interface UpdateRewardResult extends PlayerStatus {
  /** What this claim paid, for every reward the client's version reached. */
  reward: { shards: number; ids: number[] };
}
/** A scratch card: nine cells, each a shard amount in digits or an emote key. Three alike is the prize. */
export interface ScratchCard { id: number; cells: string[] }
/** Today (China date), cards left, cards since the last emote, and the card bought but not revealed yet. */
export interface ScratchState { day: string; left: number; pity: number; card: ScratchCard | null }
export interface ScratchBuyResult extends PlayerStatus { card: ScratchCard }
export interface ScratchRevealResult extends PlayerStatus {
  /** What the card paid: shards, or an item id (emote:<key>). */
  prize: { shards: number; item: string | null };
}
export interface Drop {
  item: string;
  tier?: "big" | "small" | "normal";
  rarity: Rarity;
  new: boolean;
  count: number;
  /** shards gained for a duplicate */
  shards: number;
  /** The draw was the card's holo version: `new` is then the holo version's, `cardNew` the card's. */
  holo?: boolean;
  cardNew?: boolean;
  /** A featured item of the limited pool the draw was from. */
  featured?: boolean;
}
export interface ResonanceResult extends PlayerStatus {
  drops: Drop[];
}
export interface CraftResult extends PlayerStatus {
  item: string;
}
export interface CheckinResult extends PlayerStatus {
  /** The prize drawn (index into economy.checkin.prizes), its shards and the China day it counts for. */
  prize: { index: number; shards: number; day: string };
}
/** This month's check-ins; days are China dates (YYYY-MM-DD), prize an index into economy.checkin.prizes. */
export interface CheckinMonth {
  today: string;
  available: boolean;
  days: { day: string; prize: number; shards: number }[];
}
export interface Collection {
  owned: Record<string, number>;
  recent: { item: string; rarity: string; new: boolean; ts: number }[];
}
/**
 * A drop of the save's own history. `source` is how it came: "draw", "craft" or "scratch"; `pool` the limited pool of
 * a draw there and `poolName` its name while the server still lists the pool. Drops from before the server kept
 * these carry none of them. A holo version is its own item (holo:<card id>).
 */
export interface HistoryDrop {
  id: number; item: string; rarity: string; new: boolean; ts: number; source?: string; pool?: string; poolName?: string;
}
/** A page of the history, newest first; `next` asks for the page after it, null at the end. */
export interface DropHistory { drops: HistoryDrop[]; next: number | null }
/** `showcase` is missing on servers from before profiles. `nick` and `board` (false keeps the save off the
 *  collection board) are only sent: the local settings stay as they are. */
export interface Loadout {
  character: string | null; favorites: string[]; plate: string | null; showcase?: string[]; nick?: string; board?: boolean;
}
/** A row of the collection board; `id` names the save for its profile. `cards`, `big` and `skins` count cards, big
 * hidden cards and skins; `score` is the collection score. */
export interface BoardRow {
  id: string; rank: number; nick: string; character: string; plate: string | null;
  cards: number; big: number; skins: number; score: number;
}
/** Why the asking save is off the collection board: its own choice, or no main-site account on a server with them. */
export type BoardOff = "hidden" | "account";
/** What one item is worth in the collection score, by kind. */
export type BoardPointKind = "big" | "skin" | "epic" | "limited" | "holo" | "card" | "emoteRare" | "emoteScratch" | "emoteUncommon" | "emote";
export type BoardPoints = Partial<Record<BoardPointKind, number>>;
/** The server-wide collection board by score: its top rows, the card total, the points table, and where the asking
 * save stands. */
export interface Board {
  total: number;
  points: BoardPoints;
  cards: BoardRow[];
  me: { rank: number | null; cards: number; big: number; skins: number; score: number; off: BoardOff | null };
}
export type LoadoutPatch = Partial<Loadout>;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public detail: Record<string, unknown> = {}) {
    super(message);
  }
}

export function newToken(rand: (n: number) => Uint8Array = (n) => crypto.getRandomValues(new Uint8Array(n))): string {
  return Array.from(rand(24), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The paths Api.park may reach: /api/park and /api/redeem, and below them. */
export const PARK_PATH = /^\/api\/(park|redeem)(\/[\w\-/]*)?(\?[\w=&%.\-]*)?$/;

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

/** A guest save's token, or a main-site account token for the save linked to that account. */
export type Credential = string | { bearer: string };
export function authHeaders(credential: Credential): Record<string, string> {
  return typeof credential === "string" ? { "X-Player-Token": credential } : { Authorization: `Bearer ${credential.bearer}` };
}

export interface MainUser { id: string; username: string; email: string | null }
export interface SaveSummary { shards: number; owned: number; taps: number; lastActive: number }
export interface ServerInfo { accountLogin: boolean; mainApi: string | null }
/** [daily]: shown again on the first panel opening of each China day until the player turns it off. */
/** since: when the server first saved it (unix seconds), shown as its date; absent from servers before 1.2.4. */
export interface Announcement { id: string; title: string; body: string; daily?: boolean; since?: number }
export interface ReleaseInfo {
  version: string;
  notes: string;
  /** Versions below this one are refused by the server and must update. */
  minVersion?: string | null;
  announcements?: Announcement[];
}
export interface LinkResult { user: MainUser; save: SaveSummary; linkedGuest: boolean }

export interface ActivityBatch {
  taps: number;
  session: string;
  sequence: number;
  /** Seconds left of a cooldown the input guard started, on the first batch after it trips. */
  cooldown?: number;
  /** How many of the taps other software sent; left out where the input hook cannot tell. */
  injected?: number;
}

export class Api {
  constructor(
    private base: () => string,
    private credential: () => Credential,
    private f: FetchLike = (u, i) => fetch(u, i),
  ) {}

  private async call<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await this.f(`${this.base().replace(/\/+$/, "")}${path}`, {
        method,
        headers: {
          ...(headers ?? authHeaders(this.credential())), "X-Client-Version": APP_VERSION,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (!res.ok) {
        let code = "http_error";
        let message = `服务器返回 ${res.status}`;
        let detail: Record<string, unknown> = {};
        try {
          const d = (await res.json()).detail;
          if (d?.code) {
            code = d.code;
            message = d.message || message;
            detail = d;
          }
        } catch {
          /* not json */
        }
        throw new ApiError(res.status, code, message, detail);
      }
      return (await res.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  presence = (session: string) => this.call<PlayerStatus>("POST", "/api/presence", { session });
  /** [banner]: a limited pool's id; without it the standing pool. */
  resonate = (count = 1, banner?: string) =>
    this.call<ResonanceResult>("POST", "/api/resonance/draw", banner ? { count, banner } : { count });
  me = () => this.call<PlayerStatus>("GET", "/api/me");
  /** Prices, odds and caps (src/stores/economy.ts); servers from before /api/economy carry them in the manifest. */
  economy = async (): Promise<Economy> => {
    try {
      return await this.call<Economy>("GET", "/api/economy");
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 404) throw e;
      return (await this.call<{ economy: Economy }>("GET", "/api/manifest")).economy;
    }
  };
  activity = (batch: ActivityBatch) => this.call<PlayerStatus>("POST", "/api/activity", batch);
  craft = (item: string) => this.call<CraftResult>("POST", "/api/craft", { item });
  /** A page of the save's own drops; [before] is the `next` of the page before. */
  history = (before?: number) =>
    this.call<DropHistory>("GET", `/api/resonance/history${before ? `?before=${before}` : ""}`);
  checkinMonth = () => this.call<CheckinMonth>("GET", "/api/checkin");
  checkin = () => this.call<CheckinResult>("POST", "/api/checkin");
  claimUpdateReward = () => this.call<UpdateRewardResult>("POST", "/api/update-reward");
  scratchState = () => this.call<ScratchState>("GET", "/api/scratch");
  /** Buys a card, or hands back the one still to reveal at no charge. */
  scratchBuy = () => this.call<ScratchBuyResult>("POST", "/api/scratch");
  /** Pays the card's prize; safe to repeat. */
  scratchReveal = (card: number) => this.call<ScratchRevealResult>("POST", "/api/scratch/reveal", { card });
  collection = () => this.call<Collection>("GET", "/api/collection");
  loadout = () => this.call<Loadout>("GET", "/api/loadout");
  setLoadout = (patch: LoadoutPatch) => this.call<Loadout>("POST", "/api/loadout", patch);
  board = () => this.call<Board>("GET", "/api/board?order=score");
  boardProfile = (id: string) =>
    this.call<MemberProfile>("GET", `/api/board/profile/${encodeURIComponent(id)}?showcase=${MAX_SHOWCASE}`);
  info = () => this.call<ServerInfo>("GET", "/api/info", undefined, {});
  /** The newest client release, which the server reads from the main site. */
  latestRelease = () => this.call<ReleaseInfo>("GET", "/api/client/release", undefined, {});
  account = () => this.call<{ user: MainUser; save: SaveSummary | null }>("GET", "/api/account");
  /** Any request of the park or redeem codes; other paths are refused here, before reaching the server. */
  park = <T>(method: "GET" | "POST", path: string, body?: unknown) => {
    if (!PARK_PATH.test(path)) return Promise.reject(new ApiError(0, "bad_path", "不是乐园的接口"));
    return this.call<T>(method, path, body);
  };
  /** Binds the account to this device's guest save (when given) or to a new save. */
  link = (accountToken: string, guestToken?: string) => this.call<LinkResult>("POST", "/api/account/link", {},
    { Authorization: `Bearer ${accountToken}`, ...(guestToken ? { "X-Player-Token": guestToken } : {}) });

}

/** Accumulates taps locally and reports only the count, in batches. */
export class ActivityReporter {
  private pending = 0;
  /** Of the pending taps, those other software sent; `tells` once the hook has said so for any press. */
  private pendingInjected = 0;
  private tells = false;
  private sequence = 0;
  private batch: ActivityBatch | null = null;
  private busy: Promise<boolean> | null = null;
  /** When a cooldown the server has not heard about yet ends (ms). */
  private coolUntil = 0;
  constructor(private send: (batch: ActivityBatch) => Promise<unknown>, private session = newToken()) {}

  /** Counts taps; `injected` is what the hook said of them, undefined where it cannot tell. */
  add(n = 1, injected?: boolean): void {
    this.pending = Math.min(this.pending + n, 5000 - (this.batch?.taps ?? 0));
    if (injected !== undefined) this.tells = true;
    if (injected) this.pendingInjected = Math.min(this.pendingInjected + n, this.pending);
  }
  get size(): number {
    return this.pending + (this.batch?.taps ?? 0);
  }
  /** Taps stop counting until `until` (ms); the next batch tells the server, even one without taps. */
  cool(until: number): void {
    this.coolUntil = Math.max(this.coolUntil, until);
  }
  /** Whether there is anything to send: taps, or a cooldown the server should hear about. */
  due(now = Date.now()): boolean {
    return this.size > 0 || this.coolUntil > now;
  }
  /** Send what we have; on failure the count is kept for the next try. */
  flush(now = Date.now()): Promise<boolean> {
    if (this.busy) return this.busy;
    if (!this.batch && !this.due(now)) return Promise.resolve(true);
    if (!this.batch) {
      this.batch = { taps: this.pending, session: this.session, sequence: ++this.sequence };
      if (this.tells) this.batch.injected = this.pendingInjected;
      this.pendingInjected = 0;
      const cooldown = Math.ceil((this.coolUntil - now) / 1000);
      if (cooldown > 0) this.batch.cooldown = cooldown;
      this.coolUntil = 0;
      this.pending = 0;
    }
    this.busy = this.send(this.batch).then(() => {
      this.batch = null;
      return true;
    }, () => false).finally(() => { this.busy = null; });
    return this.busy;
  }
}
