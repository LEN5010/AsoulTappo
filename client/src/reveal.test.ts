import { describe, expect, it } from "vitest";
import { boardOf, DEAL_LIMIT, groupDrops, sealed, sortDrops, spotlights, tellOf } from "./reveal";
import type { Rarity } from "./manifest";
const d = (rarity: Rarity, item = "card:test", fresh = false) => ({ rarity, item, new: fresh, count: 1, shards: 0 });

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

  it("announces only what the batch holds, best first", () => {
    expect(tellOf([d("common"), d("rare", "emote:a")])).toBe("plain");
    expect(tellOf([d("common"), d("epic")])).toBe("epic");
    expect(tellOf([d("epic"), d("skin", "char:x")])).toBe("skin");
    expect(tellOf([d("skin", "char:x"), d("legendary")])).toBe("legendary");
  });

  it("spotlights hidden cards, skins and a first animated card only", () => {
    expect(spotlights(d("legendary"), "big")).toBe(true);
    expect(spotlights(d("skin", "char:x"))).toBe(true);
    expect(spotlights(d("epic"), "small")).toBe(true);
    expect(spotlights(d("epic", "card:dance", true), "normal")).toBe(true);
    expect(spotlights(d("epic", "card:dance"), "normal")).toBe(false);
    expect(spotlights(d("rare", "emote:a", true))).toBe(false);
  });

  it("seals rare and above in a dealt batch, only spotlights in a grouped one", () => {
    expect(sealed(d("uncommon", "emote:a"), false)).toBe(false);
    expect(sealed(d("rare", "emote:a"), false)).toBe(true);
    expect(sealed(d("rare", "emote:a"), true)).toBe(false);
    expect(sealed(d("epic", "card:dance"), true, "normal")).toBe(false);
    expect(sealed(d("legendary"), true, "big")).toBe(true);
  });
});
