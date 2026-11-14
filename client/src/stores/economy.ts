// Prices, odds and caps (server/app/economy.py): not in the public repository and not bundled. The server hands them
// out at GET /api/economy once the player agreed to the terms (src/legal); each server's copy is kept in local storage,
// which both windows share, so the next start shows them before the server answers. null until the first answer:
// whatever shows a price or an odd waits for it.
import { ref, watch } from "vue";
import type { Rarity } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "./settings";

/** The client's own input guard (src/pet/TapGuard.ts): a fast second, a streak of them, and the cooldown that follows. */
export interface TapGuardRules { fastPerSecond: number; fastStreakSec: number; cooldownSec: number }

export type Economy = {
  /** Shards per day: dailyCap × (1 − e^−x), x = a·m + b·m² + c·m³ for m thousand taps and curve = [a, b, c];
   * a minute counts tapsPerMinute taps at most. */
  income: { dailyCap: number; curve: [number, number, number]; tapsPerMinute: number };
  resonance: {
    cost: number; rates: Record<Rarity, number>; pity: { legendary: number; skin: number }; commonKindWeights: { card: number; emote: number };
    /** Shards a repeat turns into: every emote, and cards by tier. */
    duplicateRefund: Partial<Record<"emote" | "big" | "small" | "normal", number>>;
    /** Tiers that keep their odds once complete, rolling repeats. */
    repeatTiers?: Rarity[];
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
    lottery?: { daily: number; closeAt: number; drawAt: number; pool: { seed: number; perCoin: number }; second: number; third: number };
  };
} & {
  /** Missing from servers before the economy left the manifest. */
  tapGuard?: TapGuardRules;
};

const KEY = "asoultappo.economy.v1";
/** Asked again after this long, so a change on the server reaches running clients. */
export const ECONOMY_MAX_AGE_MS = 30 * 60_000;

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
let cached = read(server());
export const economy = ref<Economy | null>(cached?.data ?? null);

/** Enough of an economy to show prices and odds: anything else (an error page, an unrelated answer) is ignored. */
export function isEconomy(data: unknown): data is Economy {
  const d = data as Partial<Economy> | null;
  return !!d && typeof d === "object" && typeof d.resonance?.cost === "number" && typeof d.income?.dailyCap === "number" &&
    !!d.craftCost && !!d.checkin && !!d.scratch;
}

/** The server's answer (or the desk's, relayed to the panel). */
export function setEconomy(data: Economy, from = server(), at = Date.now()): void {
  if (from !== server() || !isEconomy(data)) return;
  cached = { server: from, at, data };
  economy.value = data;
  try { localStorage.setItem(KEY, JSON.stringify(cached)); } catch { /* storage unavailable */ }
}

/** Whether it is time to ask the server again. */
export function economyDue(now = Date.now()): boolean {
  return !cached || cached.server !== server() || now - cached.at >= ECONOMY_MAX_AGE_MS;
}

// Another server: its own copy, or nothing until it answers.
watch(() => settings.serverUrl, () => {
  cached = read(server());
  economy.value = cached?.data ?? null;
}, { flush: "sync" });
