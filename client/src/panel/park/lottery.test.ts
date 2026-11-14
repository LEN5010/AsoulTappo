import { expect, it } from "vitest";
import {
  cleanNumber, countdown, dayBefore, drawLabel, dropDigit, matchedDigits, nextDraw, NO_PICKS, pickedNumber, pickLabel,
  pickTarget, putDigit, reelDigit, revealDigits, salesOpen, shortDay, stepDigit, verifyDraw, winnersLine,
} from "./lottery";

it("fills the number keys left to right, or the key picked", () => {
  let p = putDigit(NO_PICKS, null, "9");
  expect(p).toEqual({ picks: ["9", "", ""], key: 0 });
  p = putDigit(p.picks, 2, "7");
  expect(p).toEqual({ picks: ["9", "", "7"], key: 2 });
  p = putDigit(p.picks, null, "3");
  expect(p.picks).toEqual(["9", "3", "7"]);
  expect(pickTarget(p.picks, null)).toBe(null);
  expect(putDigit(p.picks, null, "1")).toEqual({ picks: ["9", "3", "7"], key: null });
  expect(pickedNumber(p.picks)).toBe("937");
  expect(pickedNumber(["9", "", "7"])).toBe(null);
});

it("clears the picked key, or the rightmost one set", () => {
  expect(dropDigit(["9", "", "7"], null)).toEqual(["9", "", ""]);
  expect(dropDigit(["9", "3", "7"], 0)).toEqual(["", "3", "7"]);
  expect(dropDigit(NO_PICKS, null)).toEqual(["", "", ""]);
});

it("steps a digit round", () => {
  expect([stepDigit("9", 1), stepDigit("0", -1), stepDigit("4", 1), stepDigit("", 1), stepDigit("", -1)])
    .toEqual(["0", "9", "5", "0", "9"]);
});

it("shows the blank keys on the pick key", () => {
  expect(pickLabel(["3", "", ""])).toEqual(["3", "_", "_"]);
  expect(pickLabel(["", "7", ""])).toEqual(["_", "7", "_"]);
  expect(pickLabel(["3", "7", "2"])).toEqual(["3", "7", "2"]);
});

it("stops selling at the local close even while the server still says open", () => {
  expect(salesOpen({ open: true, closeAt: 1000 }, 999)).toBe(true);
  expect(salesOpen({ open: true, closeAt: 1000 }, 1000)).toBe(false);
  expect(salesOpen({ open: false, closeAt: 1000 }, 500)).toBe(false);
});

it("lights a ticket's digits as the draw's digits stop, right to left", () => {
  expect(revealDigits("top", 0)).toEqual({ lit: [false, false, false], out: false });
  expect(revealDigits("top", 1)).toEqual({ lit: [false, false, true], out: false });
  expect(revealDigits("top", 3)).toEqual({ lit: [true, true, true], out: false });
  expect(revealDigits("third", 3)).toEqual({ lit: [false, false, true], out: false });
  expect(revealDigits("second", 1)).toEqual({ lit: [false, false, true], out: false });
  expect(revealDigits(null, 0)).toEqual({ lit: [false, false, false], out: false });
  expect(revealDigits(null, 1)).toEqual({ lit: [false, false, false], out: true });
});

it("spins every digit through the reel, never the same twice in a row", () => {
  for (const key of [0, 1, 2]) {
    const cells = Array.from({ length: 10 }, (_, k) => reelDigit(k + 1, key));
    expect(new Set(cells).size).toBe(10);
    cells.slice(1).forEach((d, k) => expect(d).not.toBe(cells[k]));
  }
});

it("names a draw's top prize winners, three at most", () => {
  const top = (...nicks: string[]) => nicks.map((nick) => ({ nick }));
  expect(winnersLine([])).toBe("无人");
  expect(winnersLine(top("阿草"))).toBe("阿草");
  expect(winnersLine(top("阿草", "小草", "大草"))).toBe("阿草、小草、大草");
  expect(winnersLine(top("阿草", "小草", "大草", "草草", "青草"))).toBe("阿草、小草、大草 等 5 人");
  // The board's narrow column takes one nick and the count.
  expect(winnersLine(top("阿草", "小草"), 1)).toBe("阿草 等 2 人");
  expect(winnersLine(top("阿草"), 1)).toBe("阿草");
});

it("finds the day before", () => {
  expect(dayBefore("2026-11-01")).toBe("2026-10-31");
  expect(dayBefore("2026-01-01")).toBe("2025-12-31");
});

it("marks the trailing digits a tier matched", () => {
  expect([matchedDigits("top"), matchedDigits("second"), matchedDigits("third"), matchedDigits(null)]).toEqual([3, 2, 1, 0]);
});

it("counts down to the next draw, a day later once today is drawn", () => {
  expect(countdown(1000 + 3 * 3600 + 5 * 60 + 9, 1000)).toBe("3:05:09");
  expect(countdown(1000 + 65, 1000)).toBe("1:05");
  expect(countdown(900, 1000)).toBe("0:00");
  expect(nextDraw({ drawAt: 500, drawn: false })).toBe(500);
  expect(nextDraw({ drawAt: 500, drawn: true })).toBe(500 + 86400);
});

it("keeps only three digits of what is typed", () => {
  expect(cleanNumber("0a7")).toBe("07");
  expect(cleanNumber("12345")).toBe("123");
  expect(cleanNumber("١٢٣")).toBe("");
});

it("formats a day", () => {
  expect(shortDay("2026-11-02")).toBe("11月2日");
});

it("checks a drawn number against the published hash", async () => {
  const salt = "ab".repeat(32);
  // sha256("042" + salt), as the server computes it.
  const hash = "a9c3417c257ee380a7411e693d09866ba956da2d5031ec124aa0838e681a4492";
  expect(await verifyDraw("042", salt, hash)).toBe(true);
  expect(await verifyDraw("043", salt, hash)).toBe(false);
  expect(await verifyDraw("042", salt, hash.toUpperCase())).toBe(true);
});

it("names the draw time on the China clock, with 明日 when it is on the next China day", () => {
  // 2026-11-15 19:00 China is 11:00 UTC.
  const draw = Date.UTC(2026, 10, 15, 11, 0) / 1000;
  expect(drawLabel(draw, draw - 3600)).toBe("19:00 开奖");
  // 18:59 the day before (China) and 23:59 the day before still say 明日; China midnight starts the draw's own day.
  expect(drawLabel(draw, draw - 86400 + 60)).toBe("明日 19:00 开奖");
  expect(drawLabel(draw, draw - 19 * 3600 - 60)).toBe("明日 19:00 开奖");
  expect(drawLabel(draw, draw - 19 * 3600)).toBe("19:00 开奖");
});
