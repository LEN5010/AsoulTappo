// Coin scratch cards in the park (protocol/PROTOCOL.md 游乐园 刮刮乐): reading a card's cells, how big a win is,
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
export interface ParkScratchState { card: ParkCard | null; pity: number; emotesWhole: boolean; jackpot: number }
export type PrizeTier = "again" | "shards" | "emote" | "skin" | "big" | "jackpot" | "miss";
export interface ParkPrize { tier: PrizeTier; shards: number; coins: number; item: string | null }
export interface ParkReveal extends ParkScratchState { prize: ParkPrize }

export type Cell =
  | { kind: "shards"; amount: number }
  | { kind: "emote"; key: string }
  | { kind: "again" | "skin" | "big" | "jackpot" | "blank" };

const WORDS = new Set(["again", "skin", "big", "jackpot", "blank"]);

/** A cell's symbol: an amount in digits, one of the named symbols, or an emote key. */
export function cellOf(symbol: string): Cell {
  if (/^\d+$/.test(symbol)) return { kind: "shards", amount: Number(symbol) };
  if (WORDS.has(symbol)) return { kind: symbol as "again" | "skin" | "big" | "jackpot" | "blank" };
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
 * How a win is celebrated (design §5.4): "plain" for the coins back, 1 for up to 5 times the price and an emote,
 * 2 from 16 times, 3 from 100 times, the jackpot, and a skin or big hidden card. A skin or big card the save already
 * had pays shards instead, and [prize] (once revealed) sizes it by those. 0 for a miss.
 */
export type Level = 0 | "plain" | 1 | 2 | 3;
export function levelOf(outcome: Outcome, kind: CardKind, prize?: ParkPrize | null): Level {
  if (outcome.kind === "miss" || outcome.kind === "blank") return 0;
  if (outcome.kind === "again") return "plain";
  if (outcome.kind === "emote") return 1;
  if (outcome.kind === "jackpot") return 3;
  const shards = outcome.kind === "shards" ? outcome.amount : prize && !prize.item ? prize.shards : null;
  if (shards === null) return 3;
  const times = shards / (SCRATCH.cards[kind].coins * COIN_PRICE);
  return times >= 100 ? 3 : times >= 16 ? 2 : 1;
}

/** 阿草 runs the stall and hates paying out: the bigger the win, the worse it takes it. */
export function faceOf(outcome: Outcome, level: Level): string {
  if (level === 0) return HOST.miss;
  if (outcome.kind === "emote") return HOST.emote;
  return level === "plain" ? "肯定" : level === 1 ? "收到" : level === 2 ? "惊恐" : "生无可恋";
}

export interface OddsRow {
  kind: "jackpot" | "shards" | "skin" | "big" | "emote" | "again" | "miss";
  shards?: number;
  /** Percent; for the jackpot, "coins/odds". */
  rate: string;
  /** Cards after which the row is certain, if it has a pity. */
  pity?: number;
}

const pct = (n: number) => `${Math.round(n * 1000) / 1000}%`;

/** The table of one card as the server rolls it, best first. With the emote set whole its weight goes to again. */
export function oddsRows(kind: CardKind, emotesWhole: boolean): OddsRow[] {
  const t: CardTable = SCRATCH.cards[kind];
  const odds = SCRATCH.jackpot.odds;
  const rows: OddsRow[] = [{ kind: "jackpot", rate: `${t.coins}/${odds}` }];
  const items: [number, OddsRow][] = [...t.prizes.map((p): [number, OddsRow] => [p.shards, { kind: "shards", shards: p.shards, rate: pct(p.weight) }])];
  if (t.skin) items.push([t.skin.shards, { kind: "skin", rate: pct(t.skin.weight) }]);
  if (t.big) items.push([t.big.shards, { kind: "big", rate: pct(t.big.weight) }]);
  rows.push(...items.sort((a, b) => b[0] - a[0]).map(([, row]) => row));
  const emote = t.emote?.weight ?? 0;
  if (t.emote && !emotesWhole) rows.push({ kind: "emote", rate: pct(emote), pity: t.emote.pity });
  rows.push({ kind: "again", rate: pct(t.again + (emotesWhole ? emote : 0)) });
  const won = emote + t.again + t.prizes.reduce((n, p) => n + p.weight, 0) + (t.skin?.weight ?? 0) + (t.big?.weight ?? 0);
  rows.push({ kind: "miss", rate: pct(Math.round((100 - won - (100 * t.coins) / odds) * 10) / 10) });
  return rows;
}
