import { describe, expect, it } from "vitest";
import { AWAY_MS, GREETS, LUNCH, NIGHT_LINES, NudgeClock, SPACING_MS, UNEVEN, greetLine, pick } from "./nudge";
import type { Reminder } from "./reminders";

const MIN = 60_000;
const at = (h: number, m = 0) => new Date(2026, 10, 16, h, m).getTime();
const DAY = "2026-11-16";
/** The hello of the test day already said, so the other reminders show alone. */
const GREETED = { greet: DAY };

const tip = (id: string, everyMin: number, on = true): Reminder => ({ id, name: id, on, everyMin, showSec: 30, lines: [id] });
const WATER = tip("water", 120);
const MOVE = tip("move", 60);

/** Drives the clock in 30-second ticks with input every tick while `busy`, showing whatever comes due. */
function run(clock: NudgeClock, from: number, minutes: number, busy: (t: number) => boolean = () => true) {
  const shown: { kind: string; at: number }[] = [];
  for (let t = from; t <= from + minutes * MIN; t += 30_000) {
    if (busy(t)) clock.input(t);
    const due = clock.due(t);
    if (due) { clock.shown(due, t); shown.push({ kind: due.tip?.id ?? due.kind, at: (t - from) / MIN }); }
  }
  return shown;
}
/** A reminder of [everyMin] comes this many minutes in with the earliest draw, give or take a tick. */
const earliest = (everyMin: number) => everyMin * UNEVEN[0];

describe("NudgeClock", () => {
  it("brings a reminder up after its minutes at the computer, a little early or late", () => {
    const start = at(8);
    const early = run(new NudgeClock(start, () => 0, GREETED, () => [MOVE]), start, 55);
    expect(early).toHaveLength(1);
    expect(early[0].kind).toBe("move");
    expect(early[0].at).toBeGreaterThanOrEqual(earliest(60) - 0.5);
    expect(early[0].at).toBeLessThanOrEqual(earliest(60) + 0.5);
    const late = run(new NudgeClock(start, () => 0.999, GREETED, () => [MOVE]), start, 75);
    expect(late).toHaveLength(1);
    expect(late[0].at).toBeGreaterThan(60 * UNEVEN[1] - 1);
  });

  it("starts a reminder a break answers over after a break of five minutes", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0, GREETED, () => [MOVE]);
    // a 6-minute break at minute 40
    const shown = run(clock, start, 100, (t) => t - start < 40 * MIN || t - start >= 46 * MIN);
    expect(shown).toHaveLength(1);
    expect(shown[0].at).toBeGreaterThanOrEqual(46 + earliest(60) - 0.5);
    expect(shown[0].at).toBeLessThanOrEqual(46 + earliest(60) + 0.5);
  });

  it("starts those over at a rest of the tomato timer too, and leaves the others counting", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0, GREETED, () => [MOVE, tip("my-pills", 60)]);
    for (let t = start; t < start + 40 * MIN; t += 30_000) { clock.input(t); clock.due(t); }
    clock.rested();
    const shown = run(clock, start + 40 * MIN, 30);
    expect(shown.map((s) => s.kind)).toEqual(["my-pills"]);
  });

  it("counts only while the player is there, across breaks for the reminders a break does not answer", () => {
    const start = at(15);
    // a 6-minute break every 50 minutes
    const busy = (t: number) => ((t - start) / MIN) % 50 < 44;
    const shown = run(new NudgeClock(start, () => 0, GREETED, () => [WATER]), start, 200, busy);
    expect(shown.length).toBeGreaterThan(0);
    // the minutes at the computer take longer than as many minutes with breaks in between
    expect(shown[0].at).toBeGreaterThan(earliest(120));
    expect(shown[0].at).toBeLessThan(earliest(120) + 3 * 6 + 1);
  });

  it("shows nothing while the player is away", () => {
    const start = at(9);
    const clock = new NudgeClock(start, () => 0, GREETED, () => [tip("water", 5)]);
    clock.input(start);
    expect(clock.due(start + AWAY_MS + 5 * 60 * MIN)).toBeNull();
  });

  it("leaves out a reminder that is off, and one taken off the list", () => {
    const start = at(8);
    let tips = [tip("water", 10, false), tip("my-a", 10)];
    const clock = new NudgeClock(start, () => 0, GREETED, () => tips);
    expect(run(clock, start, 25).map((s) => s.kind)).toEqual(["my-a", "my-a"]);
    tips = [tip("water", 10, false)];
    expect(run(clock, start + 25 * MIN, 30)).toEqual([]);
  });

  it("follows a change of a reminder's minutes", () => {
    const start = at(8);
    let tips = [tip("my-a", 240)];
    const clock = new NudgeClock(start, () => 0, GREETED, () => tips);
    expect(run(clock, start, 20)).toEqual([]);
    tips = [tip("my-a", 20)];
    // 20 minutes are counted already
    expect(run(clock, start + 20 * MIN + 30_000, 1).map((s) => s.kind)).toEqual(["my-a"]);
  });

  it("asks about lunch once, at the drawn minute", () => {
    const start = at(11);
    const clock = new NudgeClock(start, () => 0.5, GREETED);
    const lunch = run(clock, start, 120).filter((s) => s.kind === "lunch");
    expect(lunch).toHaveLength(1);
    const minute = LUNCH.from + Math.floor(0.5 * (LUNCH.until - LUNCH.from));
    expect(lunch[0].at).toBe(minute - 11 * 60);
    expect(clock.days.lunch).toBe(DAY);
  });

  it("does not ask about lunch again after a restart the same day", () => {
    const start = at(12);
    const clock = new NudgeClock(start, () => 0, { ...GREETED, lunch: DAY });
    expect(run(clock, start, 50).filter((s) => s.kind === "lunch")).toEqual([]);
  });

  it("gives up on lunch for the day after 13:30", () => {
    const start = at(13, 31);
    const clock = new NudgeClock(start, () => 0, GREETED);
    expect(run(clock, start, 30).filter((s) => s.kind === "lunch")).toEqual([]);
  });

  it("leaves out the once-a-day reminders the player turned off", () => {
    const start = at(11, 20);
    const clock = new NudgeClock(start, () => 0, {}, () => [], () => ({ greet: false, lunch: false, night: true }));
    expect(run(clock, start, 120)).toEqual([]);
    expect(clock.days.greet).toBe("");
  });

  it("keeps reminders ten minutes apart, the most overdue first", () => {
    const start = at(11, 20);
    // lunch drawn at 11:30 and three reminders that are due all the time
    const clock = new NudgeClock(start, () => 0, GREETED, () => [tip("my-a", 5), tip("my-b", 5), tip("my-c", 30)]);
    const shown = run(clock, start, 90);
    expect(shown.length).toBeGreaterThan(4);
    for (let i = 1; i < shown.length; i++) expect(shown[i].at - shown[i - 1].at).toBeGreaterThanOrEqual(SPACING_MS / MIN);
    const waited = new NudgeClock(start, () => 0, { ...GREETED, lunch: DAY }, () => [tip("my-c", 30), tip("my-a", 5)]);
    waited.mark(start + 30 * MIN);
    expect(run(waited, start, 41).map((s) => s.kind)).toEqual(["my-a"]);
  });

  it("holds a due reminder until it is shown", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0, GREETED, () => [MOVE]);
    let t = start;
    for (; t < start + 60 * MIN; t += 30_000) { clock.input(t); clock.due(t); }
    clock.input(t);
    expect(clock.due(t)?.tip?.id).toBe("move");
    clock.input(t + 30_000);
    expect(clock.due(t + 30_000)?.tip?.id).toBe("move");
  });
});

describe("hello and bedtime", () => {
  it("says hello the first time the player is there each day, worded for the hour", () => {
    const start = at(9, 40);
    const clock = new NudgeClock(start, () => 0, {});
    // away until 9:45
    expect(run(clock, start, 20, (t) => t >= at(9, 45))).toEqual([{ kind: "greet", at: 5 }]);
    expect(clock.days.greet).toBe(DAY);
    expect(greetLine(9 * 60, () => 0)).toBe(GREETS[0][1][0]);
    expect(greetLine(12 * 60, () => 0)).toBe(GREETS[1][1][0]);
    expect(greetLine(15 * 60, () => 0)).toBe(GREETS[2][1][0]);
    expect(greetLine(23 * 60 + 59, () => 0)).toBe(GREETS[3][1][0]);
  });

  it("does not say hello again after a restart the same day, nor before five", () => {
    expect(run(new NudgeClock(at(10), () => 0, GREETED), at(10), 9)).toEqual([]);
    const early = at(4, 50);
    // the bedtime reminder of that night was shown already
    const shown = run(new NudgeClock(early, () => 0, { night: DAY }), early, 15);
    expect(shown).toEqual([{ kind: "greet", at: 10 }]);
  });

  it("tells the player to go to bed once a night from 0:30", () => {
    const start = at(0, 10);
    const clock = new NudgeClock(start, () => 0.999, {});
    const shown = run(clock, start, 4 * 60).filter((s) => s.kind === "night");
    expect(shown).toEqual([{ kind: "night", at: 20 }]);
    expect(clock.days.night).toBe(DAY);
    expect(NIGHT_LINES.every((line) => line.length <= 12)).toBe(true);
  });

  it("keeps its distance from a bubble shown by something else", () => {
    const start = at(8);
    const clock = new NudgeClock(start, () => 0, {});
    clock.input(start);
    clock.mark(start);
    expect(clock.due(start)).toBeNull();
    clock.input(start + SPACING_MS);
    expect(clock.due(start + SPACING_MS)).toEqual({ kind: "greet" });
  });
});

describe("pick", () => {
  it("stays in the list at the edges", () => {
    expect(pick(["a", "b"], () => 0)).toBe("a");
    expect(pick(["a", "b"], () => 0.9999)).toBe("b");
    expect(pick(["a", "b"], () => 1)).toBe("b");
  });
});
