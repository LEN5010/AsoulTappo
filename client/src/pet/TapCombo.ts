// Merges a remote member's tap batches into one rising "+N" counter that fades
// out `idleMs` after the last batch (instead of one floating text per batch).
import type { Timers } from "./EmotePlayer";

export interface ComboFrame {
  count: number;
  /** changes when a new combo starts */
  seq: number;
  /** changes on every batch (for a small pop) */
  beat: number;
  /** what is counted, as an Icon name, when not the counter's own (a race win counts coins, not shards) */
  icon?: string;
}

const realTimers: Timers = {
  set: (cb, ms) => setTimeout(cb, ms),
  clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export class TapCombo {
  current: ComboFrame | null = null;
  private seq = 0;
  private beat = 0;
  private timer: unknown = null;

  constructor(private onChange: (f: ComboFrame | null) => void, private idleMs = 1200, private timers = realTimers) {}

  /** Adds [n]; a different [icon] from the running combo's starts a new one. */
  add(n: number, icon?: string): void {
    if (n <= 0) return;
    this.beat += 1;
    this.current = this.current && this.current.icon === icon
      ? { ...this.current, count: this.current.count + n, beat: this.beat }
      : { count: n, seq: ++this.seq, beat: this.beat, ...(icon ? { icon } : {}) };
    this.onChange(this.current);
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = this.timers.set(() => {
      this.timer = null;
      this.current = null;
      this.onChange(null);
    }, this.idleMs);
  }

  stop(): void {
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = null;
    this.current = null;
  }
}
