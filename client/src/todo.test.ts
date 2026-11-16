import { describe, expect, it } from "vitest";
import {
  KEEP_DONE_MS, LATE_MS, dayStrip, doneTodos, SNOOZE_MS, TITLE_MAX, completeTodo, dayText, firstTime, newTodo, nextTime, quickTimes,
  readTodos, reopenTodo, snoozeTodo, sortTodos, stepTodos, todayTodos, whenText, type Todo,
} from "./todo";

const MIN = 60_000;
/** 2026-11-16 is a Monday. */
const at = (d: number, h: number, m = 0) => new Date(2026, 10, d, h, m).getTime();
const todo = (title: string, time: number | null, repeat: Todo["repeat"] = "none", created = 0) =>
  newTodo(title, title, time, repeat, created);

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
  it("today holds what is due by midnight and what passed, and follows the date", () => {
    const list = [
      todo("昨天的", at(15, 21)), todo("今晚", at(16, 23, 59)), todo("明早", at(17, 0, 30)), todo("没时间", null),
    ];
    expect(todayTodos(list, at(16, 12)).map((t) => t.id)).toEqual(["昨天的", "今晚"]);
    // Past midnight the early one belongs to today.
    expect(todayTodos(list, at(17, 0, 5)).map((t) => t.id)).toEqual(["昨天的", "今晚", "明早"]);
  });

  it("today keeps what was ticked off today, below the open ones", () => {
    const a = completeTodo(todo("a", at(16, 9)), at(16, 10));
    const b = todo("b", at(16, 11));
    const old = completeTodo(todo("c", at(15, 9)), at(15, 10));
    expect(todayTodos([a, b, old], at(16, 12)).map((t) => t.id)).toEqual(["b", "a"]);
  });

  it("sorts open by time, untimed after, ticked off last", () => {
    const list = [completeTodo(todo("done", at(16, 8)), at(16, 9)), todo("x", null, "none", 2), todo("late", at(16, 10)),
      todo("early", at(16, 7)), todo("y", null, "none", 1)];
    expect(sortTodos(list).map((t) => t.id)).toEqual(["early", "late", "y", "x", "done"]);
  });

  it("names the day and the time", () => {
    const now = at(16, 12);
    expect(whenText(at(16, 9, 5), now)).toBe("9:05");
    expect(whenText(at(17, 20), now)).toBe("明天 20:00");
    expect(whenText(at(15, 20), now)).toBe("昨天 20:00");
    expect(dayText(at(20, 9), now)).toBe("11月20日");
  });
});

describe("quick times", () => {
  it("offer an hour on, tonight at eight and tomorrow at nine", () => {
    const q = quickTimes(at(16, 14, 30) + 20_000);
    expect(q.map((x) => x.label)).toEqual(["一小时后", "今晚 8 点", "明早 9 点"]);
    expect(q.map((x) => x.at)).toEqual([at(16, 15, 30), at(16, 20), at(17, 9)]);
  });

  it("leave tonight out after eight, and before five tomorrow morning is this morning", () => {
    expect(quickTimes(at(16, 21)).map((x) => x.key)).toEqual(["hour", "morning"]);
    expect(quickTimes(at(16, 2)).find((x) => x.key === "morning")!.at).toBe(at(16, 9));
  });
});

describe("new and stored todos", () => {
  it("trim the title, drop seconds and repeat without a time", () => {
    const t = newTodo("1", "  交  周报 ", at(16, 9) + 42_000, "daily", 0);
    expect(t.title).toBe("交 周报");
    expect(t.at).toBe(at(16, 9));
    expect(newTodo("2", "x", null, "daily", 0).repeat).toBe("none");
    expect([...newTodo("3", "长".repeat(60), null, "none", 0).title]).toHaveLength(TITLE_MAX);
  });

  it("read only well-formed todos", () => {
    const good = todo("a", at(16, 9), "weekly");
    const list = readTodos([good, { ...good }, { id: "b", title: " " }, { id: "c", title: "c", at: "x", repeat: "daily" }, null, 3]);
    expect(list.map((t) => t.id)).toEqual(["a", "c"]);
    expect(list[1]).toMatchObject({ at: null, repeat: "none", doneAt: null });
    expect(readTodos({})).toEqual([]);
  });

  it("snooze from the press, rounded to the second", () => {
    expect(snoozeTodo(todo("a", at(16, 9)), at(16, 9) + 1234).snooze).toBe(at(16, 9) + 1000 + 10 * MIN);
  });
});

describe("custom time", () => {
  it("names the next seven days", () => {
    // Monday the 16th: 今天, 明天, 后天, then Thursday on.
    const strip = dayStrip(at(16, 23, 50));
    expect(strip.map((d) => d.label)).toEqual(["今天", "明天", "后天", "周四", "周五", "周六", "周日"]);
    expect(strip.map((d) => d.date)).toEqual([16, 17, 18, 19, 20, 21, 22]);
    expect(dayStrip(at(29, 9)).map((d) => d.date)).toEqual([29, 30, 1, 2, 3, 4, 5]);
  });

  it("lists ticked-off todos latest first", () => {
    const a = completeTodo(todo("a", null), at(16, 9));
    const b = completeTodo(todo("b", null), at(16, 10));
    expect(doneTodos([a, todo("c", null), b]).map((t) => t.id)).toEqual(["b", "a"]);
  });
});
