import { describe, expect, it } from "vitest";
import { CHECKIN_LINES, STANDING_STICKERS, WHOLE_STICKERS, monthCells, padRuns, pickLine, prizeTone, reactionOf } from "./checkin";

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

describe("padRuns", () => {
  const month = (today: string) => monthCells({ today, available: true, days: [] });

  it("finds the blank runs at both ends and puts three stickers at most on them", () => {
    // November 2026: six blanks before the 1st, six after the 30th.
    const runs = padRuns(month("2026-11-09"), 11);
    expect(runs.map((r) => [r.at, r.span, r.stand])).toEqual([[0, 6, true], [36, 6, false]]);
    expect(runs.map((r) => r.stickers.length)).toEqual([2, 1]);
    expect(new Set(runs.flatMap((r) => r.stickers)).size).toBe(3);
  });

  it("leaves out an end with no blanks and gives a single blank one sticker", () => {
    // June 2026 starts on a Monday; February 2026 has one blank after the 28th.
    expect(padRuns(month("2026-06-03"), 6).map((r) => [r.at, r.span, r.stickers.length])).toEqual([[30, 5, 2]]);
    expect(padRuns(month("2026-02-15"), 2).map((r) => [r.span, r.stickers.length])).toEqual([[6, 2], [1, 1]]);
    // February 2027 fills four whole weeks.
    expect(padRuns(month("2027-02-10"), 2)).toEqual([]);
  });

  it("stands the flat-bottomed cutouts only before the 1st and puts whole figures after the last day", () => {
    for (const today of ["2026-02-15", "2026-06-03", "2026-08-20", "2026-09-10", "2026-11-09"]) {
      for (const r of padRuns(month(today), Number(today.slice(5, 7)))) {
        for (const name of r.stickers) expect(r.stand ? STANDING_STICKERS : WHOLE_STICKERS).toContain(name);
      }
    }
    expect([...STANDING_STICKERS, ...WHOLE_STICKERS]).not.toContain("微笑");
    expect([...STANDING_STICKERS, ...WHOLE_STICKERS]).not.toContain("谢谢观看");
  });

  it("picks the same stickers for a month every time", () => {
    expect(padRuns(month("2026-08-20"), 8)).toEqual(padRuns(month("2026-08-20"), 8));
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
