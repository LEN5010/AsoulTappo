// Two-form skins (a folder with formImage.webp): the pet changes into its second picture once the player has typed
// for a while, and changes back after a rest. Only key and button presses are timed, so the same rule runs for the
// own pet (its press edges) and for another member's pet (its tap batches): no message says which form is shown.
import type { Timers } from "./EmotePlayer";

export interface FormRules {
  /** typing this long without a pause longer than `gapMs` changes the form */
  holdMs: number;
  gapMs: number;
  /** this long without a press changes it back */
  restMs: number;
}

export const FORM_RULES: FormRules = { holdMs: 2000, gapMs: 1500, restMs: 3000 };

const realTimers: Timers = {
  set: (cb, ms) => setTimeout(cb, ms),
  clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export class SkinForm {
  on = false;
  private runStart = -Infinity;
  private last = -Infinity;
  private timer: unknown = null;

  constructor(
    private onChange: (on: boolean) => void,
    private rules: FormRules = FORM_RULES,
    private timers: Timers = realTimers,
  ) {}

  /** A press at [now] ms. */
  press(now: number): void {
    if (now - this.last > this.rules.gapMs) this.runStart = now;
    this.last = now;
    if (!this.on && now - this.runStart >= this.rules.holdMs) this.set(true);
    if (!this.on) return;
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = this.timers.set(() => {
      this.timer = null;
      this.set(false);
    }, this.rules.restMs);
  }

  /** Back to the first form at once, as for another skin. */
  reset(): void {
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = null;
    this.runStart = this.last = -Infinity;
    this.set(false);
  }

  private set(on: boolean): void {
    if (this.on === on) return;
    this.on = on;
    this.onChange(on);
  }
}
