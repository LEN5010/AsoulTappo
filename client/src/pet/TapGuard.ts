// Input faster than a hand can keep up, for long enough, stops counting for a while. The server applies the
// same rule to what it is sent (see protocol/PROTOCOL.md); this one answers at once and shows it on the pet.

/** Inputs in one wall-clock second that make it a fast second. */
export const FAST_PER_SECOND = 10;
/** Fast seconds in a row that start a cooldown. */
export const FAST_STREAK_SECONDS = 30;
export const COOLDOWN_MS = 60_000;

export class TapGuard {
  /** When inputs count again; in the past while they count. */
  until = 0;
  private second = -1;
  private count = 0;
  /** First second of the current run of fast seconds, -1 for none. */
  private runFrom = -1;

  /** Whether an input at `now` (ms) counts. */
  allow(now: number): boolean {
    if (now < this.until) return false;
    const s = Math.floor(now / 1000);
    if (s !== this.second) {
      const kept = s === this.second + 1 && this.count >= FAST_PER_SECOND;
      this.runFrom = kept ? (this.runFrom < 0 ? this.second : this.runFrom) : -1;
      this.second = s;
      this.count = 0;
    }
    this.count += 1;
    if (this.count >= FAST_PER_SECOND && s - (this.runFrom < 0 ? s : this.runFrom) + 1 >= FAST_STREAK_SECONDS) {
      this.cool(now + COOLDOWN_MS);
      return false;
    }
    return true;
  }

  /** Starts a cooldown ending at `until` (ms), or lengthens the current one; the server can call one too. */
  cool(until: number): void {
    if (until <= this.until) return;
    this.until = until;
    this.second = -1;
    this.count = 0;
    this.runFrom = -1;
  }
}
