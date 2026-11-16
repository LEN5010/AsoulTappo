import { describe, expect, it } from "vitest";
import {
  KEEP_DONE_MS, LATE_MS, NO_WHEN, dayStrip, doneTodos, SNOOZE_MS, TITLE_MAX, completeTodo, dayText, firstTime, hourOn, isOverdue,
  monthWeeks, newTodo, nextTime, quickHours, readTodos, renameTodo, reopenTodo, retimeTodo, snoozeTodo, sortTodos, stepTodos,
  whenOf, whenText, type Todo,
} from "./todo";

const MIN = 60_000;
/** 2026-11-16 is a Monday. */
const at = (d: number, h: number, m = 0) => new Date(2026, 10, d, h, m).getTime();
const todo = (title: string, time: number | null, repeat: Todo["repeat"] = "none", created = 0) =>
  newTodo(title, title, { at: time, allDay: false, repeat }, created);
/** An all-day todo for the day of [day], added at [now]. */
const allDay = (title: string, day: number, now: number, repeat: Todo["repeat"] = "none") =>
  newTodo(title, title, { at: day, allDay: true, repeat }, now);

describe("repeat times", () => {
  it("keep the time of day across midnight and the end of the month", () => {
    expect(nextTime(at(16, 23, 30), "daily", at(16, 23, 30))).toBe(at(17, 23, 30));
    expect(nextTime(at(30, 9), "daily", at(30, 9))).toBe(new Date(2026, 11, 1, 9).getTime());
    expect(nextTime(at(16, 9), "weekly", at(16, 9))).toBe(at(23, 9));
  });

  it("skip the weekend on working days", () => {
    // Friday 20 -> Monday 23
    expect(nextTime(at(20, 9), "weekdays", at(20, 9))).toBe(at(23, 9));
    // A working-days todo set on Saturday starts on Monday.
    expect(firstTime(at(21, 9), "weekdays")).toBe(at(23, 9));
    expect(firstTime(at(21, 9), "daily")).toBe(at(21, 9));
  });

  it("jump far ahead in one go", () => {
    const next = nextTime(at(16, 9), "daily", new Date(2028, 0, 5, 12).getTime());
    expect(next).toBe(new Date(2028, 0, 6, 9).getTime());
    const week = nextTime(at(16, 9), "weekdays", new Date(2028, 0, 7, 12).getTime());
    // 2028-01-07 is a Friday, so the next working day is Monday the 10th.
    expect(week).toBe(new Date(2028, 0, 10, 9).getTime());
  });
});

describe("ringing", () => {
  it("rings once at its time", () => {
    const t = todo("交周报", at(16, 9));
    expect(stepTodos([t], at(16, 8, 59)).onTime).toEqual([]);
    const first = stepTodos([t], at(16, 9) + 5000);
    expect(first.onTime.map((x) => x.id)).toEqual(["交周报"]);
    const again = stepTodos(first.list, at(16, 9, 1));
    expect(again.onTime).toEqual([]);
    expect(again.list).toBe(first.list);
  });

  it("counts a time that passed unseen as late: app closed, sleep or a clock set forward", () => {
    const a = todo("a", at(16, 9));
    const b = todo("b", at(16, 10));
    const c = todo("c", at(16, 18));
    const woke = stepTodos([a, b, c], at(16, 11));
    expect(woke.onTime).toEqual([]);
    expect(woke.late.map((x) => x.id)).toEqual(["a", "b"]);
    expect(stepTodos([a], at(16, 9) + LATE_MS).onTime.map((x) => x.id)).toEqual(["a"]);
    expect(stepTodos([a], at(16, 9) + LATE_MS + 1).late.map((x) => x.id)).toEqual(["a"]);
  });

  it("does not ring again when the clock is set back", () => {
    const rung = stepTodos([todo("a", at(16, 9))], at(16, 9)).list;
    expect(stepTodos(rung, at(16, 8)).list).toBe(rung);
    expect(stepTodos(rung, at(16, 9)).onTime).toEqual([]);
  });

  it("rings a snoozed todo again ten minutes later, once", () => {
    const rung = stepTodos([todo("a", at(16, 9))], at(16, 9)).list;
    const later = rung.map((t) => snoozeTodo(t, at(16, 9)));
    expect(stepTodos(later, at(16, 9) + SNOOZE_MS - 1000).onTime).toEqual([]);
    const second = stepTodos(later, at(16, 9) + SNOOZE_MS);
    expect(second.onTime.map((x) => x.id)).toEqual(["a"]);
    expect(stepTodos(second.list, at(16, 9, 30)).onTime).toEqual([]);
  });

  it("keeps a missed repeating todo overdue until ticked off, then moves it past now", () => {
    const t = todo("打卡", at(16, 9), "daily");
    const rung = stepTodos([t], at(16, 9)).list;
    // Two days later nothing rings again; it stays at Monday's time.
    const later = stepTodos(rung, at(18, 9, 30));
    expect(later.onTime).toEqual([]);
    expect(later.late).toEqual([]);
    const done = completeTodo(later.list[0], at(18, 9, 30));
    expect(done.doneAt).toBeNull();
    expect(done.at).toBe(at(19, 9));
    expect(stepTodos([done], at(19, 9)).onTime.map((x) => x.id)).toEqual(["打卡"]);
  });

  it("moves a repeating todo ticked off early past its own time", () => {
    const t = todo("打卡", at(17, 9), "daily");
    expect(completeTodo(t, at(16, 20)).at).toBe(at(18, 9));
  });

  it("drops ticked-off todos after seven days", () => {
    const done = completeTodo(todo("a", null), at(16, 9));
    expect(stepTodos([done], at(16, 9) + KEEP_DONE_MS).list).toHaveLength(1);
    expect(stepTodos([done], at(16, 9) + KEEP_DONE_MS + 1).list).toHaveLength(0);
    expect(reopenTodo(done).doneAt).toBeNull();
  });
});

describe("views", () => {
  it("sorts open by time, untimed after, ticked off last", () => {
    const now = at(16, 6);
    const list = [completeTodo(todo("done", at(16, 8)), at(16, 9)), todo("x", null, "none", 2), todo("late", at(16, 10)),
      todo("early", at(16, 7)), todo("y", null, "none", 1)];
    expect(sortTodos(list, now).map((t) => t.id)).toEqual(["early", "late", "y", "x", "done"]);
  });

  it("puts overdue ones first, and a day before the timed todos of that day", () => {
    const now = at(16, 12);
    const list = [
      allDay("明天", at(17, 0), now), todo("明早", at(17, 8)), allDay("今天", at(16, 0), now), todo("今晚", at(16, 20)),
      todo("上午", at(16, 10)), allDay("昨天", at(15, 0), at(15, 8)), todo("没时间", null),
    ];
    expect(sortTodos(list, now).map((t) => t.id)).toEqual(["昨天", "上午", "今天", "今晚", "明天", "明早", "没时间"]);
  });

  it("names the day and the time", () => {
    const now = at(16, 12);
    expect(whenText(at(16, 9, 5), false, now)).toBe("今天 09:05");
    expect(whenText(at(17, 20), false, now)).toBe("明天 20:00");
    expect(whenText(at(15, 20), false, now)).toBe("昨天 20:00");
    expect(whenText(at(17, 9), true, now)).toBe("明天");
    // Within the week: the weekday; after it the date, with the year once it is another year's.
    expect(whenText(at(20, 9), false, now)).toBe("周五 09:00");
    expect(dayText(at(22, 9), now)).toBe("周日");
    expect(dayText(at(23, 9), now)).toBe("11月23日");
    expect(dayText(at(13, 9), now)).toBe("11月13日");
    expect(dayText(new Date(2027, 0, 2).getTime(), now)).toBe("2027年1月2日");
  });
});

describe("quick hours", () => {
  it("offer nine, noon, six and eight on the chosen day, those passed today marked", () => {
    const now = at(16, 14, 30);
    expect(quickHours(at(16, 0), now).map((q) => [q.hour, q.past])).toEqual([[9, true], [12, true], [18, false], [20, false]]);
    expect(quickHours(at(17, 0), now).map((q) => q.at)).toEqual([at(17, 9), at(17, 12), at(17, 18), at(17, 20)]);
    expect(quickHours(at(17, 0), now).some((q) => q.past)).toBe(false);
  });

  it("an hour on is to the minute", () => {
    expect(hourOn(at(16, 14, 30) + 20_000)).toBe(at(16, 15, 30));
  });
});

describe("all-day todos", () => {
  it("ring at nine on their day and are overdue only once the day is over", () => {
    const t = allDay("体检", at(17, 15), at(16, 12));
    expect(t).toMatchObject({ at: at(17, 9), allDay: true, rang: null });
    expect(stepTodos([t], at(17, 8, 59)).onTime).toEqual([]);
    expect(stepTodos([t], at(17, 9)).onTime.map((x) => x.id)).toEqual(["体检"]);
    expect(isOverdue(t, at(17, 23, 59))).toBe(false);
    expect(isOverdue(t, at(18, 0))).toBe(true);
  });

  it("set for today after nine: no ring, and not overdue before midnight", () => {
    const t = allDay("买菜", at(16, 0), at(16, 14));
    expect(t.rang).toBe(t.at);
    const step = stepTodos([t], at(16, 14, 1));
    expect(step.onTime).toEqual([]);
    expect(step.late).toEqual([]);
    expect(isOverdue(t, at(16, 23, 59))).toBe(false);
    expect(isOverdue(t, at(17, 0, 1))).toBe(true);
  });

  it("set for today before nine rings at nine", () => {
    const t = allDay("买菜", at(16, 0), at(16, 7));
    expect(t.rang).toBeNull();
    expect(stepTodos([t], at(16, 9)).onTime.map((x) => x.id)).toEqual(["买菜"]);
  });

  it("repeat weekly at nine of the day after a tick", () => {
    const t = allDay("周会", at(16, 0), at(16, 14), "weekly");
    const next = completeTodo(t, at(16, 15));
    expect(next).toMatchObject({ at: at(23, 9), allDay: true, rang: null, doneAt: null });
    expect(stepTodos([next], at(23, 9)).onTime.map((x) => x.id)).toEqual(["周会"]);
  });

  it("start a working-days series set on a Saturday on the Monday", () => {
    expect(allDay("打卡", at(21, 0), at(20, 12), "weekdays").at).toBe(at(23, 9));
  });
});

describe("editing", () => {
  it("renames, keeping the old title when the new one is empty", () => {
    const t = todo("a", null);
    expect(renameTodo(t, "  b  c ").title).toBe("b c");
    expect(renameTodo(t, "   ")).toBe(t);
  });

  it("moves the time: rings afresh by the new one, the snooze dropped", () => {
    const rung = stepTodos([todo("a", at(16, 9))], at(16, 9)).list[0];
    const snoozed = snoozeTodo(rung, at(16, 9));
    const moved = retimeTodo(snoozed, { at: at(16, 15), allDay: false, repeat: "daily" }, at(16, 10));
    expect(moved).toMatchObject({ at: at(16, 15), allDay: false, repeat: "daily", rang: null, snooze: null });
    expect(stepTodos([moved], at(16, 15)).onTime).toHaveLength(1);
  });

  it("applies the all-day rule and the working days start when moved", () => {
    const t = todo("a", at(18, 9));
    expect(retimeTodo(t, { at: at(16, 0), allDay: true, repeat: "none" }, at(16, 12))).toMatchObject({ at: at(16, 9), rang: at(16, 9) });
    expect(retimeTodo(t, { at: at(21, 10), allDay: false, repeat: "weekdays" }, at(16, 12)).at).toBe(at(23, 10));
    expect(retimeTodo(t, NO_WHEN, at(16, 12))).toMatchObject({ at: null, allDay: false, repeat: "none", rang: null });
  });

  it("reads back what a todo was set to", () => {
    expect(whenOf(allDay("a", at(17, 0), at(16, 12), "daily"))).toEqual({ at: at(17, 9), allDay: true, repeat: "daily" });
  });
});

describe("new and stored todos", () => {
  it("trim the title, drop seconds and repeat without a time", () => {
    const t = newTodo("1", "  交  周报 ", { at: at(16, 9) + 42_000, allDay: false, repeat: "daily" }, 0);
    expect(t.title).toBe("交 周报");
    expect(t.at).toBe(at(16, 9));
    expect(newTodo("2", "x", { at: null, allDay: true, repeat: "daily" }, 0)).toMatchObject({ repeat: "none", allDay: false });
    expect([...newTodo("3", "长".repeat(60), NO_WHEN, 0).title]).toHaveLength(TITLE_MAX);
  });

  it("read only well-formed todos", () => {
    const good = todo("a", at(16, 9), "weekly");
    const list = readTodos([good, { ...good }, { id: "b", title: " " }, { id: "c", title: "c", at: "x", repeat: "daily" }, null, 3]);
    expect(list.map((t) => t.id)).toEqual(["a", "c"]);
    expect(list[1]).toMatchObject({ at: null, allDay: false, repeat: "none", doneAt: null });
    expect(readTodos({})).toEqual([]);
  });

  it("read todos stored before the all-day flag as timed", () => {
    const { allDay: _, ...old } = todo("a", at(16, 9));
    const [t] = readTodos([old]);
    expect(t.allDay).toBe(false);
    expect(isOverdue(t, at(16, 9))).toBe(true);
    expect(readTodos([allDay("b", at(17, 0), at(16, 12))])[0].allDay).toBe(true);
  });

  it("snooze from the press, rounded to the second", () => {
    expect(snoozeTodo(todo("a", at(16, 9)), at(16, 9) + 1234).snooze).toBe(at(16, 9) + 1000 + 10 * MIN);
  });
});

describe("custom time", () => {
  it("names the next seven days", () => {
    // Monday the 16th: 今天, 明天, then Wednesday on.
    const strip = dayStrip(at(16, 23, 50));
    expect(strip.map((d) => d.label)).toEqual(["今天", "明天", "周三", "周四", "周五", "周六", "周日"]);
    expect(strip.map((d) => d.date)).toEqual([16, 17, 18, 19, 20, 21, 22]);
    expect(strip[2].at).toBe(at(18, 0));
    expect(dayStrip(at(29, 9)).map((d) => d.date)).toEqual([29, 30, 1, 2, 3, 4, 5]);
  });

  it("lays a month out in weeks from Monday", () => {
    // November 2026 starts on a Sunday and has 30 days.
    const weeks = monthWeeks(at(16, 12));
    expect(weeks).toHaveLength(6);
    expect(weeks[0].slice(0, 6)).toEqual([null, null, null, null, null, null]);
    expect(weeks[0][6]).toBe(at(1, 0));
    expect(weeks[5][0]).toBe(at(30, 0));
    expect(weeks[5].slice(1)).toEqual([null, null, null, null, null, null]);
  });

  it("lists ticked-off todos latest first", () => {
    const a = completeTodo(todo("a", null), at(16, 9));
    const b = completeTodo(todo("b", null), at(16, 10));
    expect(doneTodos([a, todo("c", null), b]).map((t) => t.id)).toEqual(["b", "a"]);
  });
});
