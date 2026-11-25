// A scene's clock and what moves with it. Nothing here touches the page: time passes when advance() is called.
import { clamp } from "./math";

export type Ease = (t: number) => number;

// Moves start softly and settle: `out` like a damped spring, `flow` like a hand's unhurried reach.
const damped = (n: number): Ease => (t) => 1 - (1 - t) ** n * (1 + n * t);
/** `glide`: eased out of the box, quickest on the way, a long settling at the end. */
export const E = {
  glide: (t) => 1 - (1 - t ** 1.7) ** 3.2,
  linear: (t) => t,
  out: damped(4),
  quick: damped(6),
  flow: (t) => t * t * t * (t * (6 * t - 15) + 10),
} satisfies Record<string, Ease>;

type Values = Record<string, number>;
/** Some of a thing's numbers. */
export type Numbers<T> = { [K in keyof T as NonNullable<T[K]> extends number ? K : never]?: number };

interface Move {
  o: Values;
  to: Values;
  /** Where it began, and how fast it was going; null until it begins. */
  from: Values | null;
  v: Values;
  ms: number;
  ease: Ease;
  at: number;
  done: () => void;
}

export interface Timeline {
  /** Milliseconds that have passed. */
  readonly clock: number;
  /** Something is moving or waited for. */
  readonly busy: boolean;
  /** Moves some of [o]'s numbers; resolves at the end. A later move of the same number takes over as it begins. */
  tween<T extends object>(o: T, to: Numbers<T>, ms: number, ease?: Ease, delay?: number): Promise<void>;
  wait(ms: number): Promise<void>;
  advance(dt: number): void;
  /** Drops every move and wait: what they would have set stays as it is, and their promises never settle. */
  clear(): void;
}

export function createTimeline(): Timeline {
  let clock = 0;
  let tweens: Move[] = [];
  let timers: { left: number; done: () => void }[] = [];
  /** How fast each thing was going, so the next move takes over without a jolt. */
  let pace = new WeakMap<object, Values>();

  /** Where a move has a number so long after it began. */
  function where(t: Move, p: string, at: number): number {
    const k = clamp(at / t.ms);
    return t.from![p] + (t.to[p] - t.from![p]) * t.ease(k) + t.v[p] * t.ms * k * (1 - k) ** 3;
  }
  /** It goes on from where the move before it had each number at that moment: the step they change over in is one step. */
  function begin(t: Move): void {
    let v = pace.get(t.o);
    if (!v) pace.set(t.o, v = {});
    const from: Values = {};
    for (const p in t.to) {
      const before = tweens.find((u) => u !== t && u.o === t.o && u.from && p in u.to);
      from[p] = before ? where(before, p, before.at - t.at) : t.o[p] ?? 0;
      t.v[p] = v[p] ?? 0;
      if (before) delete before.to[p];
    }
    t.from = from;
  }

  return {
    get clock() { return clock; },
    get busy() { return tweens.length > 0 || timers.length > 0; },

    tween(o, to, ms, ease = E.out, delay = 0) {
      const thing = o as unknown as Values;
      for (const t of tweens) if (t.o === thing && !t.from) for (const k in to) delete t.to[k];
      return new Promise((done) => {
        tweens.push({
          o: thing, to: { ...to } as Values, from: null, v: {}, ms: Math.max(1, ms), ease, at: -delay, done,
        });
      });
    },

    wait: (ms) => new Promise((done) => { timers.push({ left: ms, done }); }),

    advance(dt) {
      clock += dt;
      for (const t of [...timers]) {
        t.left -= dt;
        if (t.left <= 0) { timers.splice(timers.indexOf(t), 1); t.done(); }
      }
      const all = [...tweens];
      for (const t of all) t.at += dt;
      for (const t of all) if (t.at >= 0 && !t.from) begin(t);
      for (const t of all) {
        if (!t.from) continue;
        const over = t.at >= t.ms, v = pace.get(t.o)!;
        for (const p in t.to) {
          const x = where(t, p, t.at);
          v[p] = over ? 0 : (x - (t.o[p] ?? 0)) / Math.max(1, dt);
          t.o[p] = x;
        }
        if (over) { tweens.splice(tweens.indexOf(t), 1); t.done(); }
      }
    },

    clear() {
      tweens = [];
      timers = [];
      pace = new WeakMap();
    },
  };
}
