import { expect, it } from "vitest";
import {
  cleanNumber, countdown, dayBefore, dropDigit, matchedDigits, nextDraw, NO_PICKS, pickedNumber, pickTarget, putDigit,
  shortDay, stepDigit, verifyDraw,
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
