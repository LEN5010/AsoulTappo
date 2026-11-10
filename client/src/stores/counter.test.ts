import { afterEach, beforeEach, expect, it, vi } from "vitest";

const storageWith = (value: unknown) => ({ getItem: () => JSON.stringify(value) });
const day = (d: number, h = 12) => new Date(2026, 10, d, h);

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.setSystemTime(day(9));
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("keeps today's count saved on the same day", async () => {
  const { load } = await import("./counter");
  expect(load(day(9), storageWith({ day: "2026-11-9", today: 5, total: 50 }))).toEqual({ day: "2026-11-9", today: 5, total: 50 });
});

it("starts a new day's count at 0 when the saved day is an earlier one", async () => {
  const { load } = await import("./counter");
  expect(load(day(10), storageWith({ day: "2026-11-9", today: 5, total: 50 }))).toEqual({ day: "2026-11-10", today: 0, total: 50 });
});

it("rolls today over at midnight while no keys are pressed", async () => {
  const { counter, bumpCounter, watchDay } = await import("./counter");
  bumpCounter(3, day(9));
  expect(counter).toMatchObject({ today: 3, total: 3 });
  vi.setSystemTime(day(9, 23));
  const stop = watchDay(60000);
  vi.advanceTimersByTime(60000);
  expect(counter.today).toBe(3);
  vi.setSystemTime(day(10, 0));
  vi.advanceTimersByTime(60000);
  expect(counter).toMatchObject({ day: "2026-11-10", today: 0, total: 3 });
  stop();
  bumpCounter(1, day(10, 1));
  expect(counter).toMatchObject({ today: 1, total: 4 });
});

it("catches up with larger server counts and never goes down", async () => {
  const { counter, bumpCounter, followServer } = await import("./counter");
  bumpCounter(10, day(9));
  followServer(500, 40, day(9));
  expect(counter).toMatchObject({ today: 40, total: 500 });
  followServer(300, 5, day(9));
  expect(counter).toMatchObject({ today: 40, total: 500 });
});

it("leaves today's count alone when the server's day is not given", async () => {
  const { counter, bumpCounter, followServer } = await import("./counter");
  bumpCounter(10, day(9));
  followServer(500, undefined, day(9));
  expect(counter).toMatchObject({ today: 10, total: 500 });
});

it("writes the local date the way the server does", async () => {
  const { serverDayName } = await import("./counter");
  expect(serverDayName(day(9))).toBe("2026-11-09");
});
