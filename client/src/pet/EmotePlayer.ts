// Emote playback for one pet: at most one bubble at a time.
//   - a different emote replaces the current one (new `seq`, the bubble swaps its picture)
//   - the same emote again bumps `count` (shown as ×N) and restarts the hold timer
//   - after `holdMs` without a new emote the bubble goes away
export interface EmoteFrame {
  key: string;
  /** changes when the picture changes */
  seq: number;
  /** repeats of the same emote in a row */
  count: number;
  /** changes on every play, also for repeats (restarts one-shot animations) */
  beat: number;
}

export interface Timers {
  set(cb: () => void, ms: number): unknown;
  clear(handle: unknown): void;
}

const realTimers: Timers = {
  set: (cb, ms) => setTimeout(cb, ms),
  clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export class EmotePlayer {
  current: EmoteFrame | null = null;
  private seq = 0;
  private beat = 0;
  private timer: unknown = null;

  constructor(
    private onChange: (frame: EmoteFrame | null) => void,
    private holdMs: () => number,
    private timers: Timers = realTimers,
  ) {}

  play(key: string): void {
    const cur = this.current;
    this.beat += 1;
    this.current = cur && cur.key === key
      ? { ...cur, count: cur.count + 1, beat: this.beat }
      : { key, seq: ++this.seq, count: 1, beat: this.beat };
    this.onChange(this.current);
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = this.timers.set(() => this.clear(), this.holdMs());
  }

  clear(): void {
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = null;
    if (this.current) {
      this.current = null;
      this.onChange(null);
    }
  }
}

/** Client-side spacing between own emotes (the server allows one per 250ms). */
export const SEND_INTERVAL_MS = 400;
