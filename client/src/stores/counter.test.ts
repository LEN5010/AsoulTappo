import { afterEach, beforeEach, expect, it, vi } from "vitest";

const storageWith = (value: unknown) => ({ getItem: () => JSON.stringify(value) });
const day = (d: number, h = 12) => new Date(Date.UTC(2026, 10, d, h - 8));

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.setSystemTime(day(9));
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("keeps today's count saved on the same day", async () => {
  const { load } = await import("./counter");
  expect(load(day(9), storageWith({ day: "2026-11-09", dayZone: "Asia/Shanghai", today: 5, total: 50 })))
    .toEqual({ day: "2026-11-09", today: 5, total: 50 });
});

it("starts a new day's count at 0 when the saved day is an earlier one", async () => {
  const { load } = await import("./counter");
  expect(load(day(10), storageWith({ day: "2026-11-09", dayZone: "Asia/Shanghai", today: 5, total: 50 })))
    .toEqual({ day: "2026-11-10", today: 0, total: 50 });
});

it.each([-480, 480])("migrates the unpadded daily count at time zone offset %s", async (offset) => {
  vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(offset);
  const { load } = await import("./counter");
  expect(load(day(9, 18), storageWith({ day: "2026-11-9", today: 5, total: 50 })))
    .toEqual({ day: "2026-11-09", today: 5, total: 50 });
});

it("carries over the lifetime count when the legacy local day starts before the China day", async () => {
  vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(-840);
  const { load } = await import("./counter");
  expect(load(day(9), storageWith({ day: "2026-11-9", today: 5, total: 50 })))
    .toEqual({ day: "2026-11-09", today: 0, total: 50 });
});

it("rolls today over at China midnight while no keys are pressed", async () => {
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
  followServer(500, { day: "2026-11-09", count: 40 }, day(9));
  expect(counter).toMatchObject({ today: 40, total: 500 });
  followServer(300, { day: "2026-11-09", count: 5 }, day(9));
  expect(counter).toMatchObject({ today: 40, total: 500 });
});

it("leaves today's count alone when the server's day is not given", async () => {
  const { counter, bumpCounter, followServer } = await import("./counter");
  bumpCounter(10, day(9));
  followServer(500, undefined, day(9));
  expect(counter).toMatchObject({ today: 10, total: 500 });
});

it("keeps the China day through midnight in Los Angeles and rolls at China midnight", async () => {
  const { counter, followServer, rollDay } = await import("./counter");
  followServer(100, { day: "2026-11-10", count: 100 }, new Date("2026-11-10T04:00:00Z"));
  rollDay(new Date("2026-11-10T08:00:05Z"));
  expect(counter).toEqual({ day: "2026-11-10", today: 100, total: 100 });
  rollDay(new Date("2026-11-10T16:00:00Z"));
  expect(counter).toEqual({ day: "2026-11-11", today: 0, total: 100 });
});

it("ignores a daily snapshot from before China midnight", async () => {
  const { counter, bumpCounter, followServer } = await import("./counter");
  bumpCounter(10, day(9));
  followServer(500, { day: "2026-11-09", count: 100 }, day(10, 0));
  expect(counter).toEqual({ day: "2026-11-10", today: 0, total: 500 });
});

it("saves the day zone with a complete server daily tap count", async () => {
  const setItem = vi.fn();
  vi.stubGlobal("localStorage", { getItem: () => null, setItem });
  const { followServer } = await import("./counter");
  followServer(200, { day: "2026-11-09", count: 200 }, day(9));
  vi.advanceTimersByTime(2000);
  expect(JSON.parse(setItem.mock.calls[0][1])).toEqual({
    day: "2026-11-09", dayZone: "Asia/Shanghai", today: 200, total: 200,
  });
});
