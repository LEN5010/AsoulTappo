import { describe, expect, it } from "vitest";
import { groupDrops, needsSummary, sortDrops, spotlightQueue } from "./reveal";
import type { Rarity } from "./manifest";
const d = (rarity: Rarity, item = "card:test", fresh = false) => ({ rarity, item, new: fresh });

describe("mixed resonance reveals", () => {
  it("sorts legendary, skin, epic, rare, common, then new before duplicates", () => {
    const drops = [d("common"), d("epic"), d("skin", "char:test"), d("legendary"), d("rare"), d("common", "card:new", true)];
    expect(sortDrops(drops).map((x) => x.rarity)).toEqual(["legendary", "skin", "epic", "rare", "common", "common"]);
    expect(sortDrops(drops)[4]!.new).toBe(true);
    expect(drops[0]!.rarity).toBe("common");
  });
  it("spotlights single cards and skins, sends single emotes to summary", () => {
    expect(spotlightQueue([d("common")])).toHaveLength(1);
    expect(spotlightQueue([d("skin", "char:test")])).toHaveLength(1);
    expect(spotlightQueue([d("rare", "emote:test")])).toEqual([]);
    expect(needsSummary([d("rare", "emote:test")])).toBe(true);
    expect(needsSummary([d("common")])).toBe(false);
  });
  it("spotlights epic dancing cards in batches", () => {
    expect(spotlightQueue([d("common"), d("epic"), d("rare", "emote:test"), d("skin", "char:test"), d("legendary")]).map((x) => x.rarity)).toEqual(["legendary", "skin", "epic"]);
    expect(needsSummary([d("common"), d("common")])).toBe(true);
  });
  it("groups repeats and sums refunds, preserving new state", () => {
    const drops = [{ ...d("common", "card:a", true), count: 1, shards: 0 }, { ...d("common", "card:a"), count: 2, shards: 40 }, { ...d("common", "card:a"), count: 3, shards: 40 }];
    expect(groupDrops(drops)).toEqual([{ ...drops[0], count: 3, shards: 80, got: 3 }]);
  });
});
