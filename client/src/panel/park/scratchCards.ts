// Coin scratch cards in the park (protocol/PROTOCOL.md 乐园 刮刮乐): reading a card's cells, how big a win is,
// 阿草's face for it, and the odds table. The server decides the prize when a card is bought; the cells only show it.
import { manifest } from "../../manifest";
import { HOST } from "../../scratch";

export const KINDS = ["basic", "premium"] as const;
export type CardKind = (typeof KINDS)[number];

const PARK = manifest.economy.park;
/** The bundled manifest always has the park; the server checks every number again. */
export const SCRATCH = PARK!.scratch!;
export const COIN_PRICE = PARK!.coin.price;
export type CardTable = (typeof SCRATCH)["cards"][CardKind];

/** A card on the table: nine cells under the coating. */
export interface ParkCard { id: number; kind: CardKind; cells: string[] }
/** What the scratch requests answer besides the status and the park. */
export interface ParkScratchState { card: ParkCard | null; pity: number; emotesWhole: boolean }
export type PrizeTier = "again" | "shards" | "emote" | "skin" | "big" | "miss";
export interface ParkPrize { tier: PrizeTier; shards: number; coins: number; item: string | null }
export interface ParkReveal extends ParkScratchState { prize: ParkPrize }

export type Cell =
  | { kind: "shards"; amount: number }
  | { kind: "emote"; key: string }
  | { kind: "again" | "skin" | "big" | "blank" };

const WORDS = new Set(["again", "skin", "big", "blank"]);

/** A cell's symbol: an amount in digits, one of the named symbols, or an emote key. */
export function cellOf(symbol: string): Cell {
  if (/^\d+$/.test(symbol)) return { kind: "shards", amount: Number(symbol) };
  if (WORDS.has(symbol)) return { kind: symbol as "again" | "skin" | "big" | "blank" };
  return { kind: "emote", key: symbol };
}

export type Outcome = { kind: "miss" } | (Cell & { at: number[] });

/** What a card pays: the symbol it shows three times and where, else a miss. */
export function outcomeOf(cells: readonly string[]): Outcome {
  for (const symbol of new Set(cells)) {
    const at = cells.flatMap((s, i) => (s === symbol ? [i] : []));
    if (at.length >= 3) return { ...cellOf(symbol), at };
  }
  return { kind: "miss" };
}

/**
 * How a win is celebrated (design §5.4): "plain" for the coins back (and less than twice the price), 1 for up to
 * 5 times the price and an emote,
 * 2 from 16 times, 3 from 100 times and a skin or big hidden card. A skin or big card the save already
 * had pays shards instead, and [prize] (once revealed) sizes it by those. 0 for a miss.
 */
export type Level = 0 | "plain" | 1 | 2 | 3;
export function levelOf(outcome: Outcome, kind: CardKind, prize?: ParkPrize | null): Level {
  if (outcome.kind === "miss" || outcome.kind === "blank") return 0;
  if (outcome.kind === "again") return "plain";
  if (outcome.kind === "emote") return 1;
  const shards = outcome.kind === "shards" ? outcome.amount : prize && !prize.item ? prize.shards : null;
  if (shards === null) return 3;
  const times = shards / (SCRATCH.cards[kind].coins * COIN_PRICE);
  // Below twice the price only on the old shard cards (200 and 500 for a 500-shard card): as plain as the coins back.
  return times >= 100 ? 3 : times >= 16 ? 2 : times >= 2 ? 1 : "plain";
}

/** 阿草 runs the stall and hates paying out: the bigger the win, the worse it takes it. */
export function faceOf(outcome: Outcome, level: Level): string {
  if (level === 0) return HOST.miss;
  if (outcome.kind === "emote") return HOST.emote;
  return level === "plain" ? "肯定" : level === 1 ? "收到" : level === 2 ? "惊恐" : "生无可恋";
}

export interface OddsRow {
  kind: "shards" | "skin" | "big" | "emote" | "again" | "miss";
  shards?: number;
  /** Percent. */
  rate: number;
  /** Cards after which the row is certain, if it has a pity. */
  pity?: number;
}

/** Weights are percentages with at most three decimals: summed in thousandths, so the miss row has no float drift. */
const milli = (n: number) => Math.round(n * 1000);

/**
 * Odds as a player reads them, one format for every row: a percent to three significant digits with at most two
 * decimals, trailing zeros dropped (0.02%, 0.5%, 3.5%, 14%, 56.5%). Rounded from thousandths, so a half rounds up.
 */
export function oddsText(rate: number): string {
  const m = milli(rate);
  if (m <= 0) return "0%";
  const decimals = Math.min(2, Math.max(0, 2 - Math.floor(Math.log10(m / 1000))));
  const step = 10 ** (3 - decimals);
  return `${Math.round(m / step) / 10 ** decimals}%`;
}

/**
 * The table of one card as the server rolls it, best prize first: the top shard prize, then the big hidden card and
 * the skin, the other shard prizes from the largest, the emote, again and the miss. With the emote set whole the emote's weight goes to again.
 */
export function oddsRows(kind: CardKind, emotesWhole: boolean): OddsRow[] {
  const t: CardTable = SCRATCH.cards[kind];
  const shards: OddsRow[] = t.prizes.map((p): OddsRow => ({ kind: "shards", shards: p.shards, rate: p.weight }))
    .sort((a, b) => (b.shards ?? 0) - (a.shards ?? 0));
  const items = (["big", "skin"] as const).flatMap((k): OddsRow[] => (t[k] ? [{ kind: k, rate: t[k]!.weight }] : []));
  const rows = [...shards.slice(0, 1), ...items, ...shards.slice(1)];
  const emote = t.emote?.weight ?? 0;
  if (t.emote && !emotesWhole) rows.push({ kind: "emote", rate: emote, pity: t.emote.pity });
  rows.push({ kind: "again", rate: (milli(t.again) + (emotesWhole ? milli(emote) : 0)) / 1000 });
  const won = rows.reduce((n, r) => n + milli(r.rate), 0);
  rows.push({ kind: "miss", rate: (100000 - won) / 1000 });
  return rows;
}

/** The card's best shard prize: the one drawn in gold. */
export const topPrize = (kind: CardKind) => Math.max(...SCRATCH.cards[kind].prizes.map((p) => p.shards));

/** The chance of a card's tier, in percent: a shard prize by its amount, or the skin or big hidden card. */
export function rateOf(kind: CardKind, tier: "skin" | "big" | number): number {
  const t: CardTable = SCRATCH.cards[kind];
  if (typeof tier === "number") return t.prizes.find((p) => p.shards === tier)?.weight ?? 0;
  return t[tier]?.weight ?? 0;
}
