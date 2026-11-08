import { describe, expect, it } from "vitest";
import { CHECKIN_LINES, monthCells, pickLine, prizeTone, reactionOf } from "./checkin";

describe("monthCells", () => {
  it("starts on Monday and pads a month that begins on Sunday", () => {
    // 2026-11-01 is a Sunday; November has 30 days.
    const cells = monthCells({ today: "2026-11-07", available: true, days: [] });
    expect(cells.slice(0, 7).map((c) => c?.day ?? null)).toEqual([null, null, null, null, null, null, 1]);
    expect(cells.filter(Boolean)).toHaveLength(30);
    expect(cells.length % 7).toBe(0);
    expect(cells.at(-1)).toBeNull();
  });

  it("marks past, today and future from the server's day and keeps what was won", () => {
    const cells = monthCells({
      today: "2026-03-15", available: false,
      days: [{ day: "2026-03-02", prize: 0, shards: 83 }, { day: "2026-03-15", prize: 5, shards: 1588 }],
    }).filter((c) => c !== null);
    expect(cells).toHaveLength(31);
    expect(cells[0]).toMatchObject({ day: 1, date: "2026-03-01", when: "past", won: undefined });
    expect(cells[1]).toMatchObject({ date: "2026-03-02", when: "past", won: { prize: 0, shards: 83 } });
    expect(cells[14]).toMatchObject({ date: "2026-03-15", when: "today", won: { prize: 5, shards: 1588 } });
    expect(cells[30]).toMatchObject({ date: "2026-03-31", when: "future" });
  });

  it("knows leap Februaries", () => {
    expect(monthCells({ today: "2028-02-10", available: true, days: [] }).filter(Boolean)).toHaveLength(29);
  });
});

describe("prizes", () => {
  it("tones the top prize gold and the next wine", () => {
    expect(prizeTone(5, 6)).toBe("tone-legendary");
    expect(prizeTone(4, 6)).toBe("tone-epic");
    expect(prizeTone(3, 6)).toBe("tone-rare");
    expect(prizeTone(0, 6)).toBe("tone-rare");
  });

  it("gives every prize its own reaction", () => {
    expect([0, 1, 2, 3, 4, 5].map((i) => reactionOf(i, 6))).toEqual(["比心", "肯定", "观察", "流汗", "生无可恋", "对不起"]);
    expect(reactionOf(0, 3)).toBe("比心");
    expect(reactionOf(2, 3)).toBe("对不起");
  });
});

describe("pickLine", () => {
  it("never says the same line twice in a row", () => {
    for (const last of CHECKIN_LINES) {
      for (const r of [0, 0.5, 0.999]) expect(pickLine(last, () => r)).not.toBe(last);
    }
    expect(pickLine("", () => 0)).toBe(CHECKIN_LINES[0]);
    expect(pickLine("", () => 0.999)).toBe(CHECKIN_LINES.at(-1));
  });
});
