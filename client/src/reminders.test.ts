import { describe, expect, it } from "vitest";
import { EVERY_MIN, LINE_MAX, LINES_MAX, PRESETS, REMINDERS_MAX, SHOW_SEC, cleanReminders, linesOf, newReminder, presetOf } from "./reminders";

describe("the built-in reminders", () => {
  it("are well formed", () => {
    expect(new Set(PRESETS.map((p) => p.id)).size).toBe(PRESETS.length);
    for (const p of PRESETS) {
      expect(p.id).toMatch(/^[a-z0-9-]{1,24}$/);
      expect(p.everyMin).toBeGreaterThanOrEqual(EVERY_MIN.min);
      expect(p.everyMin).toBeLessThanOrEqual(EVERY_MIN.max);
      expect(p.showSec).toBeGreaterThanOrEqual(SHOW_SEC.min);
      expect(p.showSec).toBeLessThanOrEqual(SHOW_SEC.max);
      expect(p.lines.length).toBeGreaterThan(0);
      expect(p.lines.length).toBeLessThanOrEqual(LINES_MAX);
      // one row of the bubble holds about this many characters beside its key
      for (const line of p.lines) expect([...line].length).toBeLessThanOrEqual(16);
    }
    expect(cleanReminders(PRESETS)).toEqual(PRESETS);
  });

  it("are what a new player has, as copies", () => {
    const list = cleanReminders(undefined);
    expect(list).toEqual(PRESETS);
    list[0].lines.push("x");
    expect(presetOf(list[0].id)!.lines).not.toContain("x");
  });
});

describe("cleanReminders", () => {
  it("keeps the player's changes and order, and adds the built-in ones the list lacks", () => {
    const mine = { id: "my-a", name: "吃药", on: true, everyMin: 240, showSec: 60, lines: ["该吃药啦"] };
    const water = { ...presetOf("water")!, on: false, everyMin: 45, lines: ["喝水"] };
    const list = cleanReminders([mine, water]);
    expect(list.slice(0, 2)).toEqual([mine, water]);
    expect(list.map((r) => r.id).sort()).toEqual(["my-a", ...PRESETS.map((p) => p.id)].sort());
  });

  it("brings numbers into range and text to length", () => {
    const [r] = cleanReminders([{ id: "my-a", name: " 一二三四五六七八九十 ", on: "yes", everyMin: 1, showSec: 9999, lines: ["  ", "a".repeat(99), 3] }]);
    expect(r).toMatchObject({ name: "一二三四五六七八", on: true, everyMin: EVERY_MIN.min, showSec: SHOW_SEC.max });
    expect(r.lines).toEqual(["a".repeat(LINE_MAX)]);
  });

  it("drops what is not a reminder, a second one of an id and those past the limit", () => {
    const many = Array.from({ length: REMINDERS_MAX + 5 }, (_, i) => ({ id: `my-${i}`, name: "a", lines: ["a"] }));
    const list = cleanReminders([null, 3, { id: "Bad Id", name: "a" }, { id: "my-x" }, many[0], ...many]);
    expect(list.filter((r) => r.id.startsWith("my-"))).toHaveLength(REMINDERS_MAX);
    expect(list.filter((r) => r.id === "my-0")).toHaveLength(1);
  });

  it("gives a built-in one its own name and lines back when they are missing", () => {
    const [water] = cleanReminders([{ id: "water", name: "别的名字", lines: [] }]);
    expect(water.name).toBe(presetOf("water")!.name);
    expect(water.lines).toEqual(presetOf("water")!.lines);
  });
});

describe("linesOf and newReminder", () => {
  it("says the name when no line says anything", () => {
    expect(linesOf({ ...newReminder([]), name: "吃药", lines: ["", "  "] })).toEqual(["吃药"]);
    expect(linesOf({ ...newReminder([]), lines: [" 一 ", ""] })).toEqual(["一"]);
  });

  it("makes an id the list does not have", () => {
    const first = newReminder([], 1000);
    expect(newReminder([first], 1000).id).not.toBe(first.id);
    expect(cleanReminders([{ ...first, lines: ["a"] }])[0].id).toBe(first.id);
  });
});
