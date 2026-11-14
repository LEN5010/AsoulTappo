import { describe, expect, it } from "vitest";
import { AWAY_MS, LUNCH, MOVE_MS, NudgeClock, SPACING_MS, WATER_MS, pick } from "./nudge";

const MIN = 60_000;
const at = (h: number, m = 0) => new Date(2026, 10, 16, h, m).getTime();

/** Drives the clock in 30-second ticks with input every tick while `busy`, showing whatever comes due. */
function run(clock: NudgeClock, from: number, minutes: number, busy: (t: number) => boolean = () => true) {
  const shown: { kind: string; at: number }[] = [];
  for (let t = from; t <= from + minutes * MIN; t += 30_000) {
    if (busy(t)) clock.input(t);
    const kind = clock.due(t);
    if (kind) { clock.shown(kind, t); shown.push({ kind, at: (t - from) / MIN }); }
  }
  return shown;
}

describe("NudgeClock", () => {
  it("asks to get up after an hour without a break", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0.999, "");
    const shown = run(clock, start, 70);
    expect(shown).toEqual([{ kind: "move", at: MOVE_MS / MIN }]);
  });

  it("starts the hour again after a break of five minutes", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0.999, "");
    // a 6-minute break at minute 40
    const shown = run(clock, start, 110, (t) => t - start < 40 * MIN || t - start >= 46 * MIN);
    expect(shown).toEqual([{ kind: "move", at: 46 + MOVE_MS / MIN }]);
  });

  it("counts water only while the player is there", () => {
    const start = at(15);
    // move reminders out of the way: a short break every 50 minutes
    const busy = (t: number) => ((t - start) / MIN) % 50 < 44;
    const clock = new NudgeClock(start, () => 0, "");
    const shown = run(clock, start, 200, busy);
    const water = shown.filter((s) => s.kind === "water");
    expect(water.length).toBeGreaterThan(0);
    // 90 minutes at the computer take longer than 90 minutes with breaks in between
    expect(water[0].at).toBeGreaterThan(WATER_MS[0] / MIN);
    expect(water[0].at).toBeLessThan(WATER_MS[0] / MIN + 3 * 6 + 1);
  });

  it("shows nothing while the player is away", () => {
    const start = at(9);
    const clock = new NudgeClock(start, () => 0, "");
    clock.input(start);
    expect(clock.due(start + AWAY_MS + 5 * 60 * MIN)).toBeNull();
  });

  it("asks about lunch once, at the drawn minute", () => {
    const start = at(11);
    const clock = new NudgeClock(start, () => 0.5, "");
    const shown = run(clock, start, 120, (t) => ((t - start) / MIN) % 50 < 44);
    const lunch = shown.filter((s) => s.kind === "lunch");
    expect(lunch).toHaveLength(1);
    const minute = LUNCH.from + Math.floor(0.5 * (LUNCH.until - LUNCH.from));
    expect(lunch[0].at).toBe(minute - 11 * 60);
    expect(clock.askedLunch).toBe("2026-11-16");
  });

  it("does not ask about lunch again after a restart the same day", () => {
    const start = at(12);
    const clock = new NudgeClock(start, () => 0, "2026-11-16");
    expect(run(clock, start, 50).filter((s) => s.kind === "lunch")).toEqual([]);
  });

  it("gives up on lunch for the day after 13:30", () => {
    const start = at(13, 31);
    const clock = new NudgeClock(start, () => 0, "");
    expect(run(clock, start, 30).filter((s) => s.kind === "lunch")).toEqual([]);
  });

  it("keeps reminders ten minutes apart", () => {
    const start = at(11, 20);
    // lunch drawn at 11:30, the hour without a break ends at 12:20 as well as water at 90 minutes, all in a row
    const clock = new NudgeClock(start, () => 0, "");
    const shown = run(clock, start, 180);
    for (let i = 1; i < shown.length; i++) expect(shown[i].at - shown[i - 1].at).toBeGreaterThanOrEqual(SPACING_MS / MIN);
  });

  it("holds a due reminder until it is shown", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0.999, "");
    let t = start;
    for (; t < start + MOVE_MS; t += 30_000) { clock.input(t); clock.due(t); }
    clock.input(t);
    expect(clock.due(t)).toBe("move");
    clock.input(t + 30_000);
    expect(clock.due(t + 30_000)).toBe("move");
  });
});

describe("pick", () => {
  it("stays in the list at the edges", () => {
    expect(pick(["a", "b"], () => 0)).toBe("a");
    expect(pick(["a", "b"], () => 0.9999)).toBe("b");
    expect(pick(["a", "b"], () => 1)).toBe("b");
  });
});
