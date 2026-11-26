import { effectScope, nextTick, type EffectScope } from "vue";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { windowVisible } from "../../stores/activity";
import { parkTry } from "../../stores/park";
import { useRaceFeed } from "./raceFeed";

vi.mock("../../stores/park", () => ({ parkTry: vi.fn() }));

const answer = {
  now: 50, nextAt: 120, race: { id: 1, phase: "betting", startsAt: 90, endsAt: 110 },
  winners: [], last: null,
};
let scope: EffectScope;
let feed: ReturnType<typeof useRaceFeed>;
let doc: EventTarget & { visibilityState: string };

function start(view?: "summary" | "schedule") {
  feed = scope.run(() => useRaceFeed({ view }))!;
  feed.start();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(10_137);
  scope = effectScope();
  doc = Object.assign(new EventTarget(), { visibilityState: "visible" });
  vi.stubGlobal("document", doc);
  windowVisible.value = true;
  vi.mocked(parkTry).mockReset().mockResolvedValue({ ok: true, data: answer });
});
afterEach(() => {
  feed.stop();
  scope.stop();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("aligns the summary to each server second after a poll changes the offset", async () => {
  vi.mocked(parkTry).mockReturnValueOnce(new Promise((resolve) => {
    setTimeout(() => resolve({ ok: true, data: answer }), 246);
  }));
  start("summary");
  await vi.advanceTimersByTimeAsync(246);
  expect(feed.now.value).toBe(Date.now());
  // The server timestamp is at the midpoint of the request, 123 ms before receipt.
  expect(feed.serverNow.value).toBe(50_123);
  for (const boundary of [51_000, 52_000, 53_000]) {
    const before = feed.serverNow.value;
    await vi.advanceTimersByTimeAsync(boundary + 9 - before);
    expect(feed.serverNow.value).toBe(before);
    await vi.advanceTimersByTimeAsync(1);
    expect(feed.serverNow.value).toBe(boundary + 10);
  }
});

it("ticks live playback every 100 ms", async () => {
  start();
  await vi.advanceTimersByTimeAsync(0);
  for (let elapsed = 0; elapsed < 400; elapsed += 100) {
    await vi.advanceTimersByTimeAsync(99);
    expect(feed.serverNow.value).toBe(50_000 + elapsed);
    await vi.advanceTimersByTimeAsync(1);
    expect(feed.serverNow.value).toBe(50_000 + elapsed + 100);
  }
});

it.each(["betting", "running"] as const)("wakes the %s reminder at its next phase boundary", async (phase) => {
  const race = { ...answer.race, phase };
  vi.mocked(parkTry).mockResolvedValue({ ok: true, data: { ...answer, race } });
  start("schedule");
  await vi.advanceTimersByTimeAsync(0);
  const boundary = phase === "betting" ? race.startsAt : race.endsAt;
  await vi.advanceTimersByTimeAsync((boundary - answer.now) * 1000 + 49);
  expect(feed.serverNow.value).toBe(answer.now * 1000);
  await vi.advanceTimersByTimeAsync(1);
  expect(feed.serverNow.value).toBe(boundary * 1000 + 50);
  // The next poll is still pending. The clock itself has no more work until the phase changes.
  expect(vi.getTimerCount()).toBe(1);
});

it.each([undefined, "summary", "schedule"] as const)("suspends %s until the document and window are both visible", async (view) => {
  start(view);
  await vi.advanceTimersByTimeAsync(0);
  const before = feed.now.value;
  windowVisible.value = false;
  await nextTick();
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(600_000);
  expect(feed.now.value).toBe(before);
  expect(parkTry).toHaveBeenCalledTimes(1);

  windowVisible.value = true;
  await nextTick();
  expect(feed.now.value).toBe(Date.now());
  expect(parkTry).toHaveBeenCalledTimes(2);

  doc.visibilityState = "hidden";
  doc.dispatchEvent(new Event("visibilitychange"));
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(600_000);
  expect(parkTry).toHaveBeenCalledTimes(2);
  doc.visibilityState = "visible";
  doc.dispatchEvent(new Event("visibilitychange"));
  expect(feed.now.value).toBe(Date.now());
  expect(parkTry).toHaveBeenCalledTimes(3);
});
