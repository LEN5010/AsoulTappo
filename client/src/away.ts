// When a member counts as away from the computer, for the status its room shows (stores/away.ts).

/** Without input for this long, a member is shown as away, ms. */
export const AWAY_AFTER_MS = 10 * 60_000;
/** A chosen status that already says there may be no input for a long while: it stays. */
export const AWAY_KEEPS: ReadonlySet<string> = new Set(["live"]);

/** Tells a stretch without input from the hand being back. Times are ms. */
export class AwayClock {
  private last: number;

  constructor(now: number) {
    this.last = now;
  }

  input(now: number): void {
    this.last = now;
  }

  /** Whether there has been no input for AWAY_AFTER_MS at [now]. */
  away(now: number): boolean {
    return now - this.last >= AWAY_AFTER_MS;
  }
}
