import { describe, expect, it } from "vitest";
import { groupDrops, needsSummary, sortDrops, spotlightQueue, type Revealed } from "./reveal";

const d = (tier: Revealed["tier"], isNew = false, id = 0) => ({ tier, new: isNew, id });

describe("sortDrops", () => {
  it("puts the rarest first and keeps draw order within a tier", () => {
    const sorted = sortDrops([d("normal", false, 1), d("small", false, 2), d("big", false, 3), d("normal", false, 4)]);
    expect(sorted.map((x) => x.id)).toEqual([3, 2, 1, 4]);
  });
  it("puts new cards before duplicates of the same tier", () => {
    expect(sortDrops([d("normal", false, 1), d("normal", true, 2)]).map((x) => x.id)).toEqual([2, 1]);
  });
  it("treats drops without a tier as normal", () => {
    expect(sortDrops([d(undefined, false, 1), d("small", false, 2)]).map((x) => x.id)).toEqual([2, 1]);
  });
  it("does not touch its input", () => {
    const drops = [d("normal"), d("big")];
    sortDrops(drops);
    expect(drops[0]!.tier).toBe("normal");
  });
});

describe("groupDrops", () => {
  const drop = (item: string, count: number, shards = 0, isNew = false) => ({ item, count, shards, new: isNew, tier: "normal" as const });

  it("merges repeats and keeps first-seen order", () => {
    const groups = groupDrops([drop("a", 1, 0, true), drop("b", 4), drop("a", 2, 3), drop("a", 3, 3)]);
    expect(groups.map((g) => g.item)).toEqual(["a", "b"]);
    expect(groups[0]).toMatchObject({ got: 3, count: 3, shards: 6, new: true });
    expect(groups[1]).toMatchObject({ got: 1, count: 4 });
  });
});

describe("spotlightQueue", () => {
  it("spotlights a single draw of any tier", () => {
    expect(spotlightQueue([d("normal")])).toHaveLength(1);
    expect(spotlightQueue([d("big")])).toHaveLength(1);
  });
  it("spotlights only hidden cards in a batch, big before small", () => {
    const queue = spotlightQueue([d("normal"), d("small", false, 1), d("normal"), d("big", false, 2)]);
    expect(queue.map((x) => x.id)).toEqual([2, 1]);
  });
  it("is empty for a batch of normal cards", () => {
    expect(spotlightQueue([d("normal"), d("normal")])).toEqual([]);
  });
});

describe("needsSummary", () => {
  it("skips the summary for a single draw", () => {
    expect(needsSummary([d("big")])).toBe(false);
    expect(needsSummary([d("normal"), d("normal")])).toBe(true);
  });
});
