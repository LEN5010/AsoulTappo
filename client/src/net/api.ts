// HTTP client for the progression API (see protocol/PROTOCOL.md). The player token is a random
// secret kept in localStorage; the server only ever stores its hash.
import { manifest } from "../manifest";

export interface PlayerStatus {
  boxes: number;
  boxesToday: number;
  progress: { taps: number; tapsPerBox: number; minutes: number; minutesPerBox: number };
  dailyCap: number;
  totals: { taps: number; activeMinutes: number; opened: number; owned: number; cards: number };
  pity: { epic: number; legendary: number };
  unlocked: string[];
  frame: string | null;
  badge: string | null;
  credited?: number;
  newBoxes?: number;
}
export interface OpenResult extends PlayerStatus {
  card: string;
  rarity: string;
  new: boolean;
  count: number;
}
export interface Collection {
  owned: Record<string, number>;
  recent: { card_id: string; rarity: string; is_new: number; ts: number }[];
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export function newToken(rand: (n: number) => Uint8Array = (n) => crypto.getRandomValues(new Uint8Array(n))): string {
  return Array.from(rand(24), (b) => b.toString(16).padStart(2, "0")).join("");
}

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export class Api {
  constructor(
    private base: () => string,
    private token: () => string,
    private f: FetchLike = (u, i) => fetch(u, i),
  ) {}

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await this.f(`${this.base().replace(/\/+$/, "")}${path}`, {
      method,
      headers: { "X-Player-Token": this.token(), ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
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
  }

  me = () => this.call<PlayerStatus>("GET", "/api/me");
  activity = (taps: number) => this.call<PlayerStatus>("POST", "/api/activity", { taps });
  openBox = () => this.call<OpenResult>("POST", "/api/boxes/open");
  collection = () => this.call<Collection>("GET", "/api/collection");
  setDecor = (patch: { frame?: string; badge?: string }) =>
    this.call<PlayerStatus>("POST", "/api/decor", patch);
}

/** Accumulates taps locally and reports only the count, in batches. */
export class ActivityReporter {
  private pending = 0;
  private busy = false;
  constructor(private send: (taps: number) => Promise<unknown>) {}

  add(n = 1): void {
    this.pending = Math.min(this.pending + n, 5000);
  }
  get size(): number {
    return this.pending;
  }
  /** Send what we have; on failure the count is kept for the next try. */
  async flush(): Promise<boolean> {
    if (this.busy) return false;
    const n = this.pending;
    this.busy = true;
    this.pending = 0;
    try {
      await this.send(n);
      return true;
    } catch {
      this.pending = Math.min(this.pending + n, 5000);
      return false;
    } finally {
      this.busy = false;
    }
  }
}

/** Series progress for the collection screen. */
export function seriesProgress(owned: Record<string, number>) {
  return manifest.series.map((s) => ({
    ...s,
    have: manifest.cards.filter((c) => c.series === s.id && (owned[c.id] ?? 0) > 0).length,
  }));
}
