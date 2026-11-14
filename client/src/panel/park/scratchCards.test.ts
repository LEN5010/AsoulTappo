import { describe, expect, it } from "vitest";
import { ACHAO } from "../../ui/achao";
import { ON_SALE, SCRATCH, cellOf, faceOf, levelOf, oddsRows, oddsText, outcomeOf, rateOf, topPrize, type Outcome } from "./scratchCards";

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
    // 200 and 500, below twice the basic card's 500 shards
    expect(levelOf(won("200"), "basic")).toBe("plain");
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
  it("reads every chance as a percent: three significant digits, two decimals at most, no trailing zeros", () => {
    expect([66.35, 56.48, 20, 15, 14, 10, 9.5, 3.5, 3, 1].map(oddsText))
      .toEqual(["66.4%", "56.5%", "20%", "15%", "14%", "10%", "9.5%", "3.5%", "3%", "1%"]);
    expect([0.6, 0.5, 0.2, 0.1, 0.05, 0.02].map(oddsText)).toEqual(["0.6%", "0.5%", "0.2%", "0.1%", "0.05%", "0.02%"]);
  });

  it("lists the basic card best prize first and moves the emote tier to again once the set is whole", () => {
    expect(oddsRows("basic", false).map((r) => [r.kind, r.shards ?? null, r.rate])).toEqual([
      ["shards", 50000, 0.1], ["shards", 8000, 0.5], ["shards", 2500, 3], ["shards", 1000, 9],
      ["shards", 500, 18], ["shards", 200, 20], ["emote", null, 5], ["again", null, 15], ["miss", null, 29.4],
    ]);
    expect(oddsRows("basic", false).map((r) => oddsText(r.rate)))
      .toEqual(["0.1%", "0.5%", "3%", "9%", "18%", "20%", "5%", "15%", "29.4%"]);
    expect(oddsRows("basic", false).find((r) => r.kind === "emote")?.pity).toBe(10);
    expect(oddsRows("basic", true).map((r) => [r.kind, r.rate]).slice(-3))
      .toEqual([["shards", 20], ["again", 20], ["miss", 29.4]]);
  });

  it("lists the premium card with its big hidden card and skin under the top prize", () => {
    expect(oddsRows("premium", false).map((r) => [r.kind, r.shards ?? null, r.rate])).toEqual([
      ["shards", 250000, 0.02], ["big", null, 0.5], ["skin", null, 0.5], ["shards", 40000, 0.5],
      ["shards", 12500, 3], ["shards", 5000, 10], ["shards", 3000, 14], ["again", null, 15], ["miss", null, 56.48],
    ]);
    expect(oddsRows("premium", false).map((r) => oddsText(r.rate)))
      .toEqual(["0.02%", "0.5%", "0.5%", "0.5%", "3%", "10%", "14%", "15%", "56.5%"]);
  });

  it("knows each card's top prize and the premium card's item odds", () => {
    expect([topPrize("basic"), topPrize("premium")]).toEqual([50000, 250000]);
    expect([rateOf("premium", 250000), rateOf("premium", "skin"), rateOf("premium", "big"), rateOf("basic", "skin")])
      .toEqual([0.02, 0.5, 0.5, 0]);
  });

  it("matches the bundled manifest", () => {
    expect(SCRATCH.cards.basic.coins).toBe(1);
    expect(SCRATCH.cards.premium.coins).toBe(5);
  });
});

describe("cards on sale", () => {
  it("leaves the hidden premium card out and keeps its table", () => {
    expect(ON_SALE).toEqual(["basic"]);
    expect(SCRATCH.cards.premium.hidden).toBe(true);
    expect(SCRATCH.cards.premium.prizes.length).toBeGreaterThan(0);
  });
});
