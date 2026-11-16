// What plays on the lottery's keys runs under one generation: bump() ends it all at once, and any timer or callback
// of an older generation does nothing. One per page instance, shared by everything that plays there.

export interface Plays {
  /** The current generation; a callback compares the one it started under. */
  readonly gen: number;
  /** Runs [fn] after [ms] unless the generation has moved on by then. */
  later(ms: number, fn: () => void): void;
  /** A new generation: every pending timer is cancelled. */
  bump(): void;
}

export function createPlays(): Plays {
  let gen = 0;
  const timers = new Set<ReturnType<typeof setTimeout>>();
  return {
    get gen() {
      return gen;
    },
    later(ms, fn) {
      const g = gen;
      const t = setTimeout(() => {
        timers.delete(t);
        if (g === gen) fn();
      }, ms);
      timers.add(t);
    },
    bump() {
      gen++;
      timers.forEach(clearTimeout);
      timers.clear();
    },
  };
}
