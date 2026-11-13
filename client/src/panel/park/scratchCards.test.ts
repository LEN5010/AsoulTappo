import { describe, expect, it } from "vitest";
import { ACHAO } from "../../ui/achao";
import { SCRATCH, cellOf, faceOf, levelOf, oddsRows, oddsText, outcomeOf, shelfRows, topPrize, type Outcome } from "./scratchCards";

const won = (cell: string): Outcome => ({ ...cellOf(cell), at: [0, 1, 2] });

describe("cells", () => {
  it("reads amounts, named symbols and emotes", () => {
    expect(cellOf("8000")).toEqual({ kind: "shards", amount: 8000 });
    expect(cellOf("again")).toEqual({ kind: "again" });
    expect(cellOf("skin")).toEqual({ kind: "skin" });
    expect(cellOf("blank")).toEqual({ kind: "blank" });
    expect(cellOf("achao.07")).toEqual({ kind: "emote", key: "achao.07" });
  });

  it("pays the symbol shown three times", () => {
    expect(outcomeOf(["skin", "5000", "skin", "again", "12500", "skin", "5000", "blank", "again"]))
      .toEqual({ kind: "skin", at: [0, 2, 5] });
    expect(outcomeOf(["blank", "5000", "blank", "again", "12500", "big", "5000", "40000", "again"])).toEqual({ kind: "miss" });
  });
});

describe("celebration", () => {
  it("grows with the times the price a card pays", () => {
    expect(levelOf({ kind: "miss" }, "basic")).toBe(0);
    expect(levelOf(won("again"), "premium")).toBe("plain");
    // an old shard card's 200 and 500
    expect(levelOf(won("500"), "basic")).toBe("plain");
    expect(levelOf(won("1000"), "basic")).toBe(1);
    expect(levelOf(won("2500"), "basic")).toBe(1);
    expect(levelOf(won("achao.01"), "basic")).toBe(1);
    expect(levelOf(won("8000"), "basic")).toBe(2);
    expect(levelOf(won("40000"), "premium")).toBe(2);
    expect(levelOf(won("50000"), "basic")).toBe(3);
    expect(levelOf(won("250000"), "premium")).toBe(3);
    expect(levelOf(won("skin"), "premium")).toBe(3);
    // a skin the save already had pays 30000, twelve times a premium card
    expect(levelOf(won("skin"), "premium", { tier: "skin", shards: 30000, coins: 0, item: null })).toBe(1);
    expect(levelOf(won("big"), "premium", { tier: "big", shards: 60000, coins: 0, item: null })).toBe(2);
    expect(levelOf(won("big"), "premium", { tier: "big", shards: 0, coins: 0, item: "card:c1" })).toBe(3);
  });

  it("gives 阿草 a cutout face for every result", () => {
    const faces = [faceOf({ kind: "miss" }, 0), faceOf(won("again"), "plain"), faceOf(won("1000"), 1),
      faceOf(won("8000"), 2), faceOf(won("250000"), 3), faceOf(won("achao.01"), 1)];
    for (const name of faces) expect(ACHAO[name], name).toMatch(/assets\/emotes\/achao\/\d\d\.webp$/);
  });
});

describe("odds", () => {
  it("reads 1% and up as a percent, less as about one in N", () => {
    expect([66.35, 57.18, 15, 14, 10, 9.5, 3.5, 3, 1].map(oddsText)).toEqual(["66%", "57%", "15%", "14%", "10%", "9.5%", "3.5%", "3%", "1%"]);
    expect([0.6, 0.5, 0.2, 0.1, 0.05, 0.02].map(oddsText)).toEqual(["1/170", "1/200", "1/500", "1/1000", "1/2000", "1/5000"]);
  });

  it("lists the basic card rarest first and moves the emote tier to again once the set is whole", () => {
    expect(oddsRows("basic", false).map((r) => [r.kind, r.shards ?? null, r.rate])).toEqual([
      ["shards", 50000, 0.05], ["shards", 8000, 0.6], ["shards", 2500, 3.5], ["emote", null, 5],
      ["shards", 1000, 9.5], ["again", null, 15], ["miss", null, 66.35],
    ]);
    expect(oddsRows("basic", false).find((r) => r.kind === "emote")?.pity).toBe(10);
    expect(oddsRows("basic", true).map((r) => [r.kind, r.rate]).slice(-2)).toEqual([["again", 20], ["miss", 66.35]]);
  });

  it("lists the premium card with its skin and big hidden card", () => {
    expect(oddsRows("premium", false).map((r) => [r.kind, r.shards ?? null, r.rate])).toEqual([
      ["shards", 250000, 0.02], ["big", null, 0.1], ["skin", null, 0.2], ["shards", 40000, 0.5],
      ["shards", 12500, 3], ["shards", 5000, 10], ["shards", 3000, 14], ["again", null, 15], ["miss", null, 57.18],
    ]);
  });

  it("puts the top end of each card on the shelf", () => {
    expect(shelfRows("premium").map((r) => r.shards ?? r.kind)).toEqual([250000, 40000, "skin", "big"]);
    expect(shelfRows("basic").map((r) => r.shards ?? r.kind)).toEqual([50000, 8000]);
    expect([topPrize("basic"), topPrize("premium")]).toEqual([50000, 250000]);
  });

  it("matches the bundled manifest", () => {
    expect(SCRATCH.cards.basic.coins).toBe(1);
    expect(SCRATCH.cards.premium.coins).toBe(5);
  });
});
