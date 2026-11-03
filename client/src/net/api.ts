// HTTP client for the progression API (see protocol/PROTOCOL.md). The player token is a random
// secret kept in localStorage; the server only ever stores its hash.
import { manifest } from "../manifest";

export interface PlayerStatus {
  draw?: { tickets: number; seconds: number; secondsPerDraw: number; pity: number; hardPity: number; total: number };
  boxes: number;
  shards: number;
  boxesToday: number;
  progress: { taps: number; tapsPerBox: number; minutes: number; minutesPerBox: number };
  dailyCap: number;
  totals: { taps: number; activeMinutes: number; opened: number; owned: number; items: number };
  pity: { epic: number; legendary: number };
  unlocked: string[];
  frame: string | null;
  badge: string | null;
  credited?: number;
  newBoxes?: number;
}
export interface Drop {
  item: string;
  tier?: "big" | "small" | "normal";
  rarity: string;
  new: boolean;
  count: number;
  /** shards gained for a duplicate */
  shards: number;
}
export interface OpenResult extends PlayerStatus {
  drops: Drop[];
}
export interface CraftResult extends PlayerStatus {
  item: string;
}
export interface Collection {
  owned: Record<string, number>;
  recent: { item: string; rarity: string; new: boolean; ts: number }[];
}
export interface Loadout { character: string | null; favorites: string[] }
export type LoadoutPatch = Partial<Loadout>;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export function newToken(rand: (n: number) => Uint8Array = (n) => crypto.getRandomValues(new Uint8Array(n))): string {
  return Array.from(rand(24), (b) => b.toString(16).padStart(2, "0")).join("");
}

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export interface ActivityBatch {
  taps: number;
  session: string;
  sequence: number;
}

export class Api {
  constructor(
    private base: () => string,
    private token: () => string,
    private f: FetchLike = (u, i) => fetch(u, i),
  ) {}

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await this.f(`${this.base().replace(/\/+$/, "")}${path}`, {
        method,
        headers: { "X-Player-Token": this.token(), ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (!res.ok) {
        let code = "http_error";
        let message = `服务器返回 ${res.status}`;
        try {
          const d = (await res.json()).detail;
          if (d?.code) {
            code = d.code;
            message = d.message || message;
          }
        } catch {
          /* not json */
        }
        throw new ApiError(res.status, code, message);
      }
      return (await res.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  presence = (session: string) => this.call<PlayerStatus>("POST", "/api/presence", { session });
  drawCards = (pool: string, count = 1) => this.call<OpenResult>("POST", "/api/cards/draw", { pool, count });
  me = () => this.call<PlayerStatus>("GET", "/api/me");
  activity = (batch: ActivityBatch) => this.call<PlayerStatus>("POST", "/api/activity", batch);
  openBoxes = (count = 1) => this.call<OpenResult>("POST", "/api/boxes/open", { count });
  craft = (item: string) => this.call<CraftResult>("POST", "/api/craft", { item });
  collection = () => this.call<Collection>("GET", "/api/collection");
  loadout = () => this.call<Loadout>("GET", "/api/loadout");
  setLoadout = (patch: LoadoutPatch) => this.call<Loadout>("POST", "/api/loadout", patch);

}

/** Accumulates taps locally and reports only the count, in batches. */
export class ActivityReporter {
  private pending = 0;
  private sequence = 0;
  private batch: ActivityBatch | null = null;
  private busy: Promise<boolean> | null = null;
  constructor(private send: (batch: ActivityBatch) => Promise<unknown>, private session = newToken()) {}

  add(n = 1): void {
    this.pending = Math.min(this.pending + n, 5000 - (this.batch?.taps ?? 0));
  }
  get size(): number {
    return this.pending + (this.batch?.taps ?? 0);
  }
  /** Send what we have; on failure the count is kept for the next try. */
  flush(): Promise<boolean> {
    if (this.busy) return this.busy;
    if (!this.batch && !this.pending) return Promise.resolve(true);
    if (!this.batch) {
      this.batch = { taps: this.pending, session: this.session, sequence: ++this.sequence };
      this.pending = 0;
    }
    this.busy = this.send(this.batch).then(() => {
      this.batch = null;
      return true;
    }, () => false).finally(() => { this.busy = null; });
    return this.busy;
  }
}

/** Series progress for the collection screen. */
export function seriesProgress(owned: Record<string, number>) {
  return manifest.series.map((s) => ({
    ...s,
    have: manifest.cards.filter((c) => c.series === s.id && (owned[`card:${c.id}`] ?? 0) > 0).length,
  }));
}
