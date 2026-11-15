import { describe, expect, it } from "vitest";
import { DEFAULT_PLAN, LONG_EVERY, clockText, pomodoroDone, pomodoroLine, pomodoroNotice, readPomodoro, startPomodoro, stepPomodoro, type Pomodoro, type PomodoroBubble } from "./pomodoro";

const MIN = 60_000;
const plan = DEFAULT_PLAN;

describe("pomodoro", () => {
  it("rests after the focus and asks to go again after the rest", () => {
    const p = startPomodoro(1000, plan);
    expect(p).toEqual({ phase: "focus", from: 1000, until: 1000 + 25 * MIN, round: 1 });
    expect(stepPomodoro(p, p.until - 1, plan)).toEqual({ pomodoro: p, bubble: null });
    const rest = stepPomodoro(p, p.until, plan);
    expect(rest).toEqual({ pomodoro: { phase: "rest", from: p.until, until: p.until + 5 * MIN, round: 1, long: false }, bubble: "rest" });
    expect(stepPomodoro(rest.pomodoro, rest.pomodoro!.until, plan)).toEqual({ pomodoro: null, bubble: "again" });
    expect(stepPomodoro(null, 5, plan)).toEqual({ pomodoro: null, bubble: null });
  });

  it("uses the lengths set for it", () => {
    const own = { ...plan, focusMin: 50, restMin: 10 };
    const p = startPomodoro(0, own);
    expect(p.until).toBe(50 * MIN);
    expect(stepPomodoro(p, p.until, own).pomodoro).toEqual({ phase: "rest", from: 50 * MIN, until: 60 * MIN, round: 1, long: false });
  });

  it("takes the long rest every few rounds, and only with long rests on", () => {
    const p = startPomodoro(0, plan, LONG_EVERY);
    expect(stepPomodoro(p, p.until, plan).pomodoro).toEqual({ phase: "rest", from: p.until, until: p.until + 15 * MIN, round: LONG_EVERY, long: true });
    expect(stepPomodoro(p, p.until, { ...plan, long: false }).pomodoro).toMatchObject({ until: p.until + 5 * MIN, long: false });
    expect(stepPomodoro({ ...p, round: LONG_EVERY + 1 }, p.until, plan).pomodoro).toMatchObject({ long: false });
    // A plain rest set longer than the long one: the long rest is not the shorter.
    const slow = { ...plan, restMin: 20 };
    expect(stepPomodoro(p, p.until, slow).pomodoro).toMatchObject({ until: p.until + 20 * MIN, long: true });
  });

  it("starts the next focus by itself when set to", () => {
    const auto = { ...plan, auto: true };
    const rest: Pomodoro = { phase: "rest", from: 0, until: 1000, round: 2, long: false };
    expect(stepPomodoro(rest, 1000, auto)).toEqual({ pomodoro: { phase: "focus", from: 1000, until: 1000 + 25 * MIN, round: 3 }, bubble: "back" });
  });

  it("stops without a word when found after the next phase would have ended", () => {
    const p = startPomodoro(0, plan);
    expect(stepPomodoro(p, p.until + 5 * MIN, plan)).toEqual({ pomodoro: null, bubble: null });
    expect(stepPomodoro({ phase: "rest", from: 0, until: 0, round: 1 }, 5 * MIN, plan)).toEqual({ pomodoro: null, bubble: null });
    expect(stepPomodoro({ phase: "rest", from: 0, until: 0, round: 1 }, 25 * MIN, { ...plan, auto: true })).toEqual({ pomodoro: null, bubble: null });
  });

  it("tells how much of the phase has gone", () => {
    const p = startPomodoro(0, plan);
    expect(pomodoroDone(p, 0)).toBe(0);
    expect(pomodoroDone(p, p.until / 2)).toBe(0.5);
    expect(pomodoroDone(p, p.until + 1)).toBe(1);
    expect(pomodoroDone({ ...p, from: p.until }, 0)).toBe(1);
  });

  it("words the system notice like the bubble, except the question it cannot ask", () => {
    const rest: Pomodoro = { phase: "rest", from: 0, until: 0, round: 1, long: false };
    expect(pomodoroNotice("rest", rest, plan)).toBe(pomodoroLine("rest", rest, plan));
    expect(pomodoroNotice("back", null, plan)).toBe("休息结束，开始专注");
    expect(pomodoroNotice("again", null, plan)).toBe("休息结束，可以再来一轮");
  });

  it("shows the time left as m:ss", () => {
    expect(clockText(25 * MIN)).toBe("25:00");
    expect(clockText(61_000)).toBe("1:01");
    expect(clockText(400)).toBe("0:01");
    expect(clockText(-5)).toBe("0:00");
  });

  it("reads back only a stored timer", () => {
    expect(readPomodoro({ phase: "rest", from: 2, until: 5, round: 4, long: true })).toEqual({ phase: "rest", from: 2, until: 5, round: 4, long: true });
    expect(readPomodoro({ phase: "focus", until: 5 })).toEqual({ phase: "focus", from: 5, until: 5, round: 1 });
    expect(readPomodoro({ phase: "focus", from: 9, until: 5, round: 0 })).toEqual({ phase: "focus", from: 5, until: 5, round: 1 });
    for (const bad of [null, "x", { phase: "nap", until: 5 }, { phase: "focus", until: "5" }, { phase: "focus", until: Infinity }]) {
      expect(readPomodoro(bad)).toBeNull();
    }
  });

  it("says the rest's length and keeps its lines to one row with keys", () => {
    const rest: Pomodoro = { phase: "rest", from: 0, until: 0, round: 1, long: false };
    expect(pomodoroLine("rest", rest, { ...plan, restMin: 10 })).toBe("专注完成，休息 10 分钟");
    expect(pomodoroLine("rest", { ...rest, long: true }, plan)).toBe("专注完成，长休息 15 分钟");
    const widest = { ...plan, restMin: 60 };
    for (const bubble of ["rest", "back", "again"] satisfies PomodoroBubble[]) {
      for (const long of [false, true]) expect(pomodoroLine(bubble, { ...rest, long }, widest).length).toBeLessThanOrEqual(15);
    }
  });
});
