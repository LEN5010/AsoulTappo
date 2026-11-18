import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PlayerStatus } from "../net/api";
import { withEconomy } from "../test/economy";

const playerStatus = (over: Partial<PlayerStatus> = {}): PlayerStatus => ({
  player: "p1",
  shards: 5000,
  income: { day: "2026-11-18", today: 0, cap: 10400, taps: 0, perTap: 1, multiplier: 1, perMinute: 60 },
  resonance: { pity: { legendary: 0, skin: 0 }, hardPity: { legendary: 400, skin: 200 }, total: 0 },
  totals: { taps: 0, activeMinutes: 0, owned: 0, items: 0 },
  ...over,
});

let pet: typeof import("./pet") | undefined;
let player: typeof import("./player") | undefined;

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-18T12:00:00Z"));
  vi.stubGlobal("localStorage", { getItem: withEconomy(() => null), setItem: () => {} });
});

afterEach(async () => {
  pet?.stopPet();
  player?.stopReporting();
  await vi.advanceTimersByTimeAsync(0);
  pet = undefined;
  player = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("pet cooldown tracking", () => {
  it("renews the cooldown when consecutive statuses carry the same remaining seconds", async () => {
    player = await import("./player");
    pet = await import("./pet");
    const t0 = Date.now();
    player.status.value = playerStatus({ tapCooldown: 60 });
    await nextTick();
    expect(pet.tapCooldown.value).toBe(t0 + 60_000);
    pet.onInput({ kind: "key_down" });
    expect([pet.tapStats.blocked, pet.tapStats.counted]).toEqual([1, 0]);

    // No intermediate tapCooldown: 0 arrives before another 60 s cooldown starts.
    vi.advanceTimersByTime(70_000);
    const t1 = Date.now();
    player.status.value = playerStatus({ tapCooldown: 60 });
    await nextTick();
    expect(pet.tapCooldown.value).toBe(t1 + 60_000);
    pet.onInput({ kind: "key_down" });
    expect([pet.tapStats.blocked, pet.tapStats.counted]).toEqual([2, 0]);

    // A shorter countdown in a later status does not shorten the active cooldown.
    vi.advanceTimersByTime(5_000);
    player.status.value = playerStatus({ tapCooldown: 10 });
    await nextTick();
    expect(pet.tapCooldown.value).toBe(t1 + 60_000);

    vi.advanceTimersByTime(55_000);
    pet.onInput({ kind: "key_down" });
    expect([pet.tapStats.blocked, pet.tapStats.counted]).toEqual([2, 1]);
  });
});
