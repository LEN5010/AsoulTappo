import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmotePlayer, type EmoteFrame } from "./EmotePlayer";
import { TapCombo, type ComboFrame } from "./TapCombo";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("EmotePlayer", () => {
  it("replaces different emotes, counts repeats and hides after the hold time", () => {
    const frames: (EmoteFrame | null)[] = [];
    const p = new EmotePlayer((f) => frames.push(f), () => 1000);
    p.play("a");
    p.play("b");
    expect(frames.map((f) => f && [f.key, f.seq, f.count])).toEqual([["a", 1, 1], ["b", 2, 1]]);
    vi.advanceTimersByTime(900);
    p.play("b");
    expect(p.current).toMatchObject({ key: "b", seq: 2, count: 2 });
    vi.advanceTimersByTime(900); // the repeat restarted the hold timer
    expect(p.current).not.toBeNull();
    vi.advanceTimersByTime(100);
    expect(p.current).toBeNull();
    expect(frames.at(-1)).toBeNull();
  });
  it("gives every play a new beat and starts a new picture after clearing", () => {
    const p = new EmotePlayer(() => {}, () => 500);
    p.play("a");
    const first = p.current!.beat;
    p.play("a");
    expect(p.current!.beat).toBeGreaterThan(first);
    p.clear();
    p.play("a");
    expect(p.current).toMatchObject({ seq: 2, count: 1 });
  });
});

describe("TapCombo", () => {
  it("adds batches into one counter until it goes idle", () => {
    const frames: (ComboFrame | null)[] = [];
    const c = new TapCombo((f) => frames.push(f), 1200);
    c.add(3);
    vi.advanceTimersByTime(1000);
    c.add(4);
    expect(c.current).toMatchObject({ count: 7, seq: 1 });
    vi.advanceTimersByTime(1200);
    expect(c.current).toBeNull();
    c.add(0);
    expect(c.current).toBeNull();
    c.add(2);
    expect(c.current).toMatchObject({ count: 2, seq: 2 });
    expect(frames.filter((f) => f === null)).toHaveLength(1);
  });
});
