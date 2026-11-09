import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { incomeTip, tapShards } from "../income";
import type { PlayerStatus } from "../net/api";

const income = (taps: number, today: number, perTap: number) =>
  ({ income: { today, cap: 10400, taps, perTap, multiplier: 1, perMinute: perTap * 60 } }) as PlayerStatus;

describe("tap income", () => {
  it("follows the log curve and stops at the daily cap", () => {
    expect(Math.round(tapShards(1000))).toBe(1941);
    expect(Math.round(tapShards(10000))).toBe(6714);
    expect(tapShards(60000)).toBe(10400);
  });
  it("reads today's progress and the next tap's value, and nothing from older servers", () => {
    expect(incomeTip(income(2820, 4556, 0.89))).toBe("今日已获得 4,556 · 敲一下 +0.89");
    expect(incomeTip(income(0, 0, 3.4))).toBe("今日已获得 0 · 敲一下 +3.4");
    expect(incomeTip(income(45000, 10400, 0))).toBe("今日已获得 10,400 · 今日已满");
    expect(incomeTip({ income: { multiplier: 8, perMinute: 48 } } as PlayerStatus)).toBeUndefined();
  });
});

describe("shard pop", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.resetModules();
  });

  async function fresh(taps: number | undefined) {
    const player = await import("./player");
    player.status.value = taps === undefined ? null : income(taps, Math.floor(tapShards(taps)), 0);
    const pop = await import("./shardPop");
    return pop;
  }

  it("adds whole predicted shards, at most 120 taps a minute", async () => {
    const { popShards, shardCombo } = await fresh(0);
    const minute = Date.UTC(2026, 10, 10, 4, 0, 0);
    for (let i = 0; i < 10; i++) popShards(minute + i);
    // 2800 × ln(1.01) = 27.9
    expect(shardCombo.value?.count).toBe(27);
    for (let i = 10; i < 200; i++) popShards(minute + i);
    // 2800 × ln(1.12) = 317.3
    expect(shardCombo.value?.count).toBe(317);
  });

  it("starts from the server's count of today's taps", async () => {
    const { popShards, shardCombo } = await fresh(42200);
    popShards(Date.now());
    expect(shardCombo.value).toBeNull();
  });

  it("follows the server when its day starts over", async () => {
    const { popShards, shardCombo } = await fresh(42200);
    const player = await import("./player");
    player.status.value = income(20, 66, 3.24);
    await nextTick();
    popShards(Date.now());
    // 2800 × (ln 1.021 − ln 1.020) = 2.7
    expect(shardCombo.value?.count).toBe(2);
  });

  it("skips a count the server sent for the day before", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    // 00:00:05 on 11-11 in China; the status still counts 11-10.
    vi.setSystemTime(Date.UTC(2026, 10, 10, 16, 0, 5));
    const { popShards, shardCombo } = await fresh(0);
    const player = await import("./player");
    player.status.value = { income: { day: "2026-11-10", today: 1653, cap: 10400, taps: 800, perTap: 1.556, multiplier: 1, perMinute: 93.3 } } as PlayerStatus;
    await nextTick();
    for (let i = 0; i < 10; i++) popShards(Date.now() + i);
    expect(shardCombo.value?.count).toBe(27);
  });

  it("shows nothing for a server without tap income", async () => {
    const { popShards, shardCombo } = await fresh(undefined);
    popShards(Date.now());
    expect(shardCombo.value).toBeNull();
  });
});
