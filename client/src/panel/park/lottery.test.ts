import { expect, it } from "vitest";
import { cleanNumber, countdown, matchedDigits, nextDraw, shortDay, verifyDraw } from "./lottery";

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
