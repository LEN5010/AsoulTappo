// Scratch card logic: reading a card's cells, the odds table, 阿草's faces and how much of the coating is gone.
// The server decides the prize when a card is bought (see protocol/PROTOCOL.md); the cells only show it.
import { manifest } from "./manifest";

const CFG = manifest.economy.scratch;
export const SCRATCH_EMOTES = manifest.emoteSets.find((s) => s.id === CFG.emote.set)?.emotes ?? [];

export type Cell = { kind: "shards"; amount: number } | { kind: "emote"; key: string };

/** A cell's symbol: a shard amount in digits, or an emote key. */
export function cellOf(symbol: string): Cell {
  return /^\d+$/.test(symbol) ? { kind: "shards", amount: Number(symbol) } : { kind: "emote", key: symbol };
}

export type Outcome = { kind: "miss" } | ((Cell & { at: number[] }));

/** What a card pays: the symbol it shows three times and where, else a miss. */
export function outcomeOf(cells: string[]): Outcome {
  for (const symbol of new Set(cells)) {
    const at = cells.flatMap((s, i) => (s === symbol ? [i] : []));
    if (at.length >= 3) return { ...cellOf(symbol), at };
  }
  return { kind: "miss" };
}

/** Draw tone of a win, as on the check-in calendar: gold for the top prize, wine for the next, coral below. */
export function toneOf(outcome: Outcome): "" | "tone-rare" | "tone-epic" | "tone-legendary" {
  if (outcome.kind === "miss") return "";
  if (outcome.kind === "emote") return "tone-epic";
  const amounts = CFG.prizes.map((p) => p.shards).sort((a, b) => a - b);
  if (outcome.amount >= amounts[amounts.length - 1]!) return "tone-legendary";
  if (amounts.length > 1 && outcome.amount >= amounts[amounts.length - 2]!) return "tone-epic";
  return "tone-rare";
}

/**
 * 阿草 runs the stall and hates paying out. Cutouts only, and none with lettering low in the picture: it stands
 * big in the head, cut off at the waist by the sheet (微笑 and 谢谢观看 are framed pictures; 才八点 and 晚安 carry words).
 */
export const HOST = { open: "招商", watching: "观察", closed: "拒绝", miss: "比心", emote: "对不起" } as const;
/** Smallest shard prize first: the more it pays, the worse 阿草 takes it. */
const SHARD_FACES = ["肯定", "收到", "流汗", "惊恐", "生无可恋"];

/** 阿草's sticker for a revealed card. */
export function faceOf(outcome: Outcome): string {
  if (outcome.kind === "miss") return HOST.miss;
  if (outcome.kind === "emote") return HOST.emote;
  const amounts = CFG.prizes.map((p) => p.shards).sort((a, b) => a - b);
  const index = Math.max(0, amounts.filter((a) => a <= outcome.amount).length - 1);
  const at = amounts.length > 1 ? Math.round((index / (amounts.length - 1)) * (SHARD_FACES.length - 1)) : 0;
  return SHARD_FACES[at]!;
}

/** The emote key of one of 阿草's stickers by name, for showing it over a pet. */
export const faceKey = (name: string) => SCRATCH_EMOTES.find((e) => e.name === name)?.key;

export interface OddsRow {
  /** Shards the row pays; null for the emote row and the miss row. */
  shards: number | null;
  kind: "emote" | "shards" | "miss";
  /** Percent. */
  rate: number;
  /** Cards after which the row is certain, if it has a pity. */
  pity?: number;
}

/** The odds as the server rolls them, best first. With the whole set owned there is no emote tier: its weight misses. */
export function oddsRows(complete: boolean): OddsRow[] {
  const emote: OddsRow[] = complete ? [] : [{ kind: "emote", shards: null, rate: CFG.emote.weight, pity: CFG.emote.pity }];
  const prizes = [...CFG.prizes].sort((a, b) => b.shards - a.shards)
    .map((p): OddsRow => ({ kind: "shards", shards: p.shards, rate: p.weight }));
  const miss = 100 - (complete ? 0 : CFG.emote.weight) - CFG.prizes.reduce((n, p) => n + p.weight, 0);
  return [...emote, ...prizes, { kind: "miss", shards: null, rate: Math.round(miss * 1000) / 1000 }];
}

/** Emote keys of the set a save owns. */
export function ownedScratchEmotes(owned: Record<string, number>): string[] {
  return SCRATCH_EMOTES.filter((e) => (owned[`emote:${e.key}`] ?? 0) > 0).map((e) => e.key);
}

/** A box on the card, in 0..1 of its width and height. */
export interface Box { x0: number; y0: number; x1: number; y1: number }

/**
 * How much of a card's coating has been scratched off, on a coarse grid over the unit square: cheaper than
 * reading the canvas back, and the same on every screen density. With [boxes] (the cells under the coating) it
 * also tells how far the least scratched one is uncovered.
 */
export class Coating {
  private cleared: Uint8Array;
  private count = 0;
  /** The box each grid square's centre lies in, -1 for none. */
  private owner: Int16Array;
  private boxTotal: number[];
  private boxCleared: number[];

  constructor(private n = 24, boxes: Box[] = []) {
    this.cleared = new Uint8Array(n * n);
    this.owner = new Int16Array(n * n).fill(-1);
    this.boxTotal = boxes.map(() => 0);
    this.boxCleared = boxes.map(() => 0);
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const x = (i + 0.5) / n;
        const y = (j + 0.5) / n;
        const b = boxes.findIndex((r) => x >= r.x0 && x < r.x1 && y >= r.y0 && y < r.y1);
        if (b < 0) continue;
        this.owner[j * n + i] = b;
        this.boxTotal[b]! += 1;
      }
    }
  }

  /** A round brush of radius `r` dragged from (x0, y0) to (x1, y1); all in 0..1 of the card. Returns the share cleared. */
  stroke(x0: number, y0: number, x1: number, y1: number, r: number): number {
    const steps = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / (r / 2)));
    for (let s = 0; s <= steps; s++) this.dab(x0 + ((x1 - x0) * s) / steps, y0 + ((y1 - y0) * s) / steps, r);
    return this.share;
  }

  private dab(x: number, y: number, r: number): void {
    const n = this.n;
    const lo = (v: number) => Math.max(0, Math.floor((v - r) * n));
    const hi = (v: number) => Math.min(n - 1, Math.ceil((v + r) * n));
    for (let j = lo(y); j <= hi(y); j++) {
      for (let i = lo(x); i <= hi(x); i++) {
        const k = j * n + i;
        if (this.cleared[k]) continue;
        if (Math.hypot((i + 0.5) / n - x, (j + 0.5) / n - y) <= r) {
          this.cleared[k] = 1;
          this.count += 1;
          const b = this.owner[k]!;
          if (b >= 0) this.boxCleared[b]! += 1;
        }
      }
    }
  }

  get share(): number {
    return this.count / this.cleared.length;
  }

  /** The share uncovered of the least scratched box; the whole card's share when there are no boxes. */
  get least(): number {
    let least = Infinity;
    this.boxTotal.forEach((total, b) => {
      if (total) least = Math.min(least, this.boxCleared[b]! / total);
    });
    return least === Infinity ? this.share : least;
  }
}
