import { describe, expect, it } from "vitest";
import { boardOf, DEAL_LIMIT, groupDrops, newItems, sealed, sortDrops, spotlights } from "./reveal";
import type { Rarity } from "./manifest";
const d = (rarity: Rarity, item = "card:test", fresh = false) =>
  ({ rarity, item, new: fresh, count: 1, shards: 0 } as { rarity: Rarity; item: string; new: boolean; count: number; shards: number; holo?: boolean; cardNew?: boolean });

describe("resonance reveal", () => {
  it("sorts rarity tiers including uncommon, then new before duplicates", () => {
    const drops = [d("common"), d("epic"), d("skin", "char:test"), d("legendary"), d("rare"), d("uncommon"), d("common", "card:new", true)];
    expect(sortDrops(drops).map((x) => x.rarity)).toEqual(["legendary", "skin", "epic", "rare", "uncommon", "common", "common"]);
    expect(sortDrops(drops)[5]!.new).toBe(true);
    expect(drops[0]!.rarity).toBe("common");
  });

  it("groups repeats and sums refunds, preserving new state", () => {
    const drops = [{ ...d("common", "emote:a", true), count: 1 }, { ...d("common", "emote:a"), count: 2, shards: 10 }, { ...d("common", "emote:a"), count: 3, shards: 10 }];
    expect(groupDrops(drops)).toEqual([{ ...drops[0], count: 3, shards: 20, got: 3 }]);
  });

  it("deals small batches in draw order and groups big ones rarest first", () => {
    const ten = [d("common", "emote:a"), d("legendary"), ...Array.from({ length: DEAL_LIMIT - 2 }, () => d("common", "emote:a"))];
    expect(boardOf(ten).map((x) => x.rarity)).toEqual(ten.map((x) => x.rarity));
    expect(boardOf(ten).every((x) => x.got === 1)).toBe(true);
    const big = [...ten, d("rare", "emote:b")];
    expect(boardOf(big).map((x) => [x.item, x.got])).toEqual([["card:test", 1], ["emote:b", 1], ["emote:a", 9]]);
  });

  it("spotlights hidden cards, skins and a first animated or limited card only", () => {
    expect(spotlights(d("legendary"), "big")).toBe(true);
    expect(spotlights(d("skin", "char:x"))).toBe(true);
    expect(spotlights(d("epic"), "small")).toBe(true);
    expect(spotlights(d("epic", "card:dance", true), "normal")).toBe(true);
    expect(spotlights(d("epic", "card:dance"), "normal")).toBe(false);
    expect(spotlights(d("rare", "emote:a", true))).toBe(false);
    expect(spotlights(d("limited", "card:closet", true), "normal")).toBe(true);
    expect(spotlights(d("limited", "card:closet"), "normal")).toBe(false);
  });

  it("seals every tile in a dealt batch, spotlights and animated emotes in a grouped one", () => {
    expect(sealed(d("uncommon", "emote:a"), false)).toBe(true);
    expect(sealed(d("common", "card:a"), false)).toBe(true);
    expect(sealed(d("common", "emote:a", true), true)).toBe(false);
    expect(sealed(d("rare", "emote:a"), true)).toBe(true);
    expect(sealed(d("uncommon", "emote:a"), true)).toBe(false);
    expect(sealed(d("epic", "card:dance"), true, "normal")).toBe(false);
    expect(sealed(d("legendary"), true, "big")).toBe(true);
  });

  describe("holo versions", () => {
    const holo = (fresh: boolean, cardNew = false) => ({ ...d("common", "card:h", fresh), holo: true, cardNew });

    it("spotlight a first holo version only, whatever the card was", () => {
      expect(spotlights(holo(true, true), "normal")).toBe(true);
      expect(spotlights(holo(true, false), "normal")).toBe(true);
      expect(spotlights(holo(false), "normal")).toBe(false);
      expect(spotlights(d("common", "card:h", true), "normal")).toBe(false);
    });

    it("stay sealed in a grouped board so they turn with their light", () => {
      expect(sealed(holo(false), true, "normal")).toBe(true);
      expect(sealed(d("common", "card:h"), true, "normal")).toBe(false);
    });

    it("read just after limited cards and keep apart from plain draws of the card", () => {
      const drops = [d("common", "card:h"), d("rare", "emote:r"), holo(false), d("limited", "card:w"), d("common", "card:h")];
      expect(sortDrops(drops).map((x) => [x.rarity, !!x.holo])).toEqual([
        ["limited", false], ["common", true], ["rare", false], ["common", false], ["common", false],
      ]);
      const grouped = groupDrops([d("common", "card:h"), holo(true, true), d("common", "card:h"), holo(false)]);
      expect(grouped.map((x) => [x.item, !!x.holo, x.got, x.new])).toEqual([
        ["card:h", false, 2, false], ["card:h", true, 2, true],
      ]);
      expect(grouped[1]!.cardNew).toBe(true);
    });

    it("count the card as a second new item when it came with its holo version", () => {
      expect(newItems([holo(true, true)])).toBe(2);
      expect(newItems([holo(true, false), holo(false), d("common", "card:x", true), d("common", "card:y")])).toBe(2);
    });
  });
});
