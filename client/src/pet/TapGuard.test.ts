import { describe, expect, it } from "vitest";
import { COOLDOWN_MS, TapGuard } from "./TapGuard";

/** `perSecond` evenly spaced inputs every second for `seconds` seconds from `from` (ms); how many counted. */
function run(guard: TapGuard, from: number, seconds: number, perSecond: number): number {
  let counted = 0;
  for (let s = 0; s < seconds; s++) {
    for (let i = 0; i < perSecond; i++) if (guard.allow(from + s * 1000 + (i * 1000) / perSecond)) counted++;
  }
  return counted;
}

describe("TapGuard", () => {
  it("lets a hand's pace through however long it lasts", () => {
    const guard = new TapGuard();
    expect(run(guard, 0, 600, 9)).toBe(600 * 9);
    expect(guard.until).toBe(0);
  });

  it("stops counting for a minute after thirty fast seconds in a row", () => {
    const guard = new TapGuard();
    // The tenth input of the thirtieth second trips it.
    expect(run(guard, 0, 30, 12)).toBe(29 * 12 + 9);
    expect(guard.until).toBe(29_000 + (9 * 1000) / 12 + COOLDOWN_MS);
    expect(guard.allow(guard.until - 1)).toBe(false);
    expect(guard.allow(guard.until)).toBe(true);
  });

  it("starts over after a slow second or a silent one", () => {
    const guard = new TapGuard();
    run(guard, 0, 29, 12);
    run(guard, 29_000, 1, 5);
    expect(run(guard, 30_000, 29, 12)).toBe(29 * 12);
    expect(guard.allow(70_000)).toBe(true);
    expect(run(guard, 71_000, 29, 12)).toBe(29 * 12);
    expect(guard.until).toBe(0);
  });

  it("holds a cooldown the server called and never shortens one", () => {
    const guard = new TapGuard();
    guard.cool(50_000);
    guard.cool(20_000);
    expect(guard.until).toBe(50_000);
    expect(guard.allow(49_999)).toBe(false);
    expect(guard.allow(50_000)).toBe(true);
  });
});
