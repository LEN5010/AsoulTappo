// Prices, odds and caps (server/app/economy.py): not in the public repository and not bundled. The server hands them
// out at GET /api/economy once the player agreed to the terms (src/legal); each server's copy is kept in local storage,
// which both windows share, so the next start shows them before the server answers. null until the first answer:
// whatever shows a price or an odd waits for it.
import { ref, watch } from "vue";
import type { Rarity } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "./settings";
import { STANDALONE } from "../edition";

/** The client's own input guard (src/pet/TapGuard.ts): a fast second, a streak of them, and the cooldown that follows. */
export interface TapGuardRules { fastPerSecond: number; fastStreakSec: number; cooldownSec: number }

/** One level of the park's tile matching: the board, its kinds (4 tiles each), time, shift, top prize and hints. */
export interface LinkLevel {
  rows: number; cols: number; kinds: number; seconds: number;
  shift: "none" | "down" | "left" | "center"; max: number; hints: number;
}
export interface LinkConfig { entry: number; grace: number; account: boolean; sets: string[]; levels: LinkLevel[] }

/**
 * Photocard boxes of one series (server/app/photocards.py): a box costs `price` shards and holds `size` cards, one of
 * them rare for certain and each other one at `rare` percent. A save buys `daily` a China day; at 0 the series is on
 * the shelf but not sold. `split` weighs what a rare card is. The `signPity`-th box since the last one with a signed
 * card has one for certain, until the save holds them all. `swap` repeats of signed cards are traded for one the save
 * lacks; `refund` is what other repeats turn into, and signed ones once the save holds them all.
 */
export interface PhotocardConfig {
  series: string; price: number; size: number; daily: number; rare: number;
  split: Record<"duo" | "group" | "sign", number>;
  signPity: number; swap: number; refund: { solo: number; rare: number };
}

/**
 * A limited pool (server/app/banners.py): the standing pool with `items` in a tier of their own, drawn at `rate`
 * percent and for certain on the `pity`-th draw since the last one. `start` and `end` are seconds.
 */
/**
 * A limited pool (server/app/banners.py). `rates`: odds of its own for some tiers, common taking the rest. `share`:
 * the percent of a tier's draws that are its featured items of that tier. `rate`: a featured tier of its own.
 */
export interface Banner {
  id: string; name: string; start: number; end: number; items: string[];
  rate?: number; rates?: Partial<Record<Rarity, number>>; share?: number; pity?: number;
}

export type Economy = {
  /** Shards per day: dailyCap × (1 − e^−x), x = a·m + b·m² + c·m³ for m thousand taps and curve = [a, b, c];
   * a minute counts tapsPerMinute taps at most. */
  income: { dailyCap: number; curve: [number, number, number]; tapsPerMinute: number };
  resonance: {
    /** An older server names no limited tier. */
    cost: number; rates: Record<Exclude<Rarity, "limited">, number> & { limited?: number }; pity: { legendary: number; skin: number }; commonKindWeights: { card: number; emote: number };
    /** Shards a repeat turns into: every emote, and cards by tier. */
    duplicateRefund: Partial<Record<"emote" | "big" | "small" | "normal", number>>;
    /** Tiers that keep their odds once complete, rolling repeats. */
    repeatTiers?: Rarity[];
    /** Percent of draws of a card with a holo version that are that version; none without it. */
    holoChance?: number;
    /** Limited pools this client can draw from now or within the hour (resonance.ts). */
    banners?: Banner[];
    /** Item ids a limited pool keeps out of the standing pool, running or yet to start. */
    held?: string[];
  };
  craftCost: Partial<Record<Rarity, number>>;
  /** Daily check-in prizes, smallest first; weights are percentages. A prize pays its shards give or take `spread`. */
  checkin: { prizes: { shards: number; weight: number }[]; spread: number };
  /**
   * Scratch cards: `price` shards each, `daily` a China day. Weights are percentages; the rest of 100 wins nothing.
   * The emote tier gives a missing emote of `set`, for certain on the `pity`-th card since the last one. Once the
   * set is whole the tier and its pity are gone and its weight wins nothing. The room is told about `announce`
   * shards or more.
   */
  scratch: {
    price: number;
    daily: number;
    prizes: { shards: number; weight: number }[];
    emote: { set: string; weight: number; pity: number };
    announce: number;
  };
  /**
   * Rock-paper-scissors in rooms: both pay `bet`, the winner gets `prize`. An invite waits `inviteSec`, a round
   * `throwSec`. A save's net win of a China day stays at or below `dailyWinCap`; both saves need `minTaps` taps in
   * all.
   */
  duel?: {
    stakes: { bet: number; prize: number }[];
    inviteSec: number;
    throwSec: number;
    dailyWinCap: number;
    minTaps: number;
  };
  /**
   * Dou dizhu in rooms: `stakes` are the base stakes, each seat deposits base × capMult × 2 (the most a landlord
   * loses) and the multiplier stops at `capMult`. `rake` percent of what the winners win is burnt. A save whose net
   * win of a China day reached `dailyWinCap` starts no more games that day; the three saves need `minTaps` taps in
   * all. With `counter` the card counter is sold: `coins` park coins buy `games` games of it. Missing on servers
   * without the game.
   */
  doudizhu?: {
    stakes: number[];
    capMult: number;
    rake: number;
    inviteSec: number;
    bidSec: number;
    playSec: number;
    againSec: number;
    dailyWinCap: number;
    minTaps: number;
    counter?: { coins: number; games: number };
  };
  /** The park (server/app/economy.py explains every field). Missing on servers without one. */
  park?: {
    /**
     * Coins: `price` shards each, as many as the shards pay for, `gift` free a day. Buying and the gift need
     * `minTaps` taps in all. Every `stampsPerCoin` stamps make a coin; `badges` are the stamp totals of the three
     * badges.
     */
    coin: { price: number; gift: number; minTaps: number; stampsPerCoin: number; badges: number[] };
    /** Coin scratch cards (park_scratch.py): weights are percentages, the rest of 100 misses. A `hidden` card is off sale. */
    scratch?: {
      cards: Record<"basic" | "premium", {
        hidden?: boolean; coins: number; again: number; first: number; prizes: { shards: number; weight: number }[];
        emote?: { set: string; weight: number; pity: number }; skin?: { weight: number; shards: number }; big?: { weight: number; shards: number };
      }>;
      roomAt: Record<"basic" | "premium", number>;
      serverAt: Record<"basic" | "premium", number>;
    };
    race?: import("../panel/park/race").RaceConfig;
    /** secondEach: shards each second prize ticket wins; servers before it share `second` of the sales instead. */
    lottery?: {
      daily: number; closeAt: number; drawAt: number; pool: { seed: number; perCoin: number };
      secondEach?: number; second?: number; third: number;
    };
    /**
     * Tile matching (park_link.py): `entry` shards a game, `levels.length` games a day, game n plays `levels[n-1]`.
     * Tiles are static emotes of `sets`. With `account` a game needs a bound account.
     */
    link?: LinkConfig;
  };
  /** In shelf order, a series at most once. Missing or empty on servers without photocards. */
  photocards?: PhotocardConfig[];
} & {
  /** Missing from servers before the economy left the manifest. */
  tapGuard?: TapGuardRules;
};

const KEY = "asoultappo.economy.v1";
/** Asked again after this long, so a change on the server reaches running clients. */
export const ECONOMY_MAX_AGE_MS = 30 * 60_000;
const BANNER_RECHECK_MS = 60_000;

interface Cached { server: string; at: number; data: Economy }

function read(server: string): Cached | null {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "null") as Cached | null;
    return raw && raw.server === server && isEconomy(raw.data) ? raw : null;
  } catch {
    return null;
  }
}

const server = () => toHttpBase(settings.serverUrl);
// The standalone edition has no economy: nothing is priced and nothing shows odds.
let cached = STANDALONE ? null : read(server());
export const economy = ref<Economy | null>(cached?.data ?? null);

/** Enough of an economy to show prices and odds: anything else (an error page, an unrelated answer) is ignored. */
export function isEconomy(data: unknown): data is Economy {
  const d = data as Partial<Economy> | null;
  return !!d && typeof d === "object" && typeof d.resonance?.cost === "number" && typeof d.income?.dailyCap === "number" &&
    !!d.craftCost && !!d.checkin && !!d.scratch;
}

/** The server's answer (or the desk's, relayed to the panel). */
export function setEconomy(data: Economy, from = server(), at = Date.now()): void {
  if (STANDALONE || from !== server() || !isEconomy(data)) return;
  cached = { server: from, at, data };
  economy.value = data;
  try { localStorage.setItem(KEY, JSON.stringify(cached)); } catch { /* storage unavailable */ }
}

/** Whether it is time to ask the server again. */
export function economyDue(now = Date.now()): boolean {
  const current = cached;
  if (!current || current.server !== server() || now - current.at >= ECONOMY_MAX_AGE_MS) return true;
  return !!current.data.resonance.banners?.some((b) => {
    const end = b.end * 1000;
    return end <= now && (current.at < end || now - current.at >= BANNER_RECHECK_MS);
  });
}

// Another server: its own copy, or nothing until it answers.
watch(() => settings.serverUrl, () => {
  if (STANDALONE) return;
  cached = read(server());
  economy.value = cached?.data ?? null;
}, { flush: "sync" });
