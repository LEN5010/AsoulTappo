/**
 * Accumulates tap COUNTS (never which key) and flushes them as one integer
 * every `intervalMs` (default 150ms, valid range 100–200ms) while there is
 * something pending. Counts above `maxBatch` are split into several sends.
 */
export class TapBatcher {
  private pending = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly send: (count: number) => void,
    private readonly intervalMs = 150,
    private readonly maxBatch = 500,
  ) {}

  add(n = 1): void {
    if (n <= 0) return;
    this.pending += n;
    if (this.timer === null) {
      this.timer = setTimeout(() => this.flush(), this.intervalMs);
    }
  }

  flush(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    while (this.pending > 0) {
      const n = Math.min(this.pending, this.maxBatch);
      this.pending -= n;
      this.send(n);
    }
  }

  /** Drop anything pending (e.g. when disconnected / left the room). */
  clear(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.pending = 0;
  }
}
