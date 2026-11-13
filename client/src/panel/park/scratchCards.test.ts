import { describe, expect, it } from "vitest";
import { ACHAO } from "../../ui/achao";
import { SCRATCH, cellOf, faceOf, levelOf, oddsRows, outcomeOf, type Outcome } from "./scratchCards";

const won = (cell: string): Outcome => ({ ...cellOf(cell), at: [0, 1, 2] });

describe("cells", () => {
  it("reads amounts, named symbols and emotes", () => {
    expect(cellOf("8000")).toEqual({ kind: "shards", amount: 8000 });
    expect(cellOf("again")).toEqual({ kind: "again" });
    expect(cellOf("jackpot")).toEqual({ kind: "jackpot" });
    expect(cellOf("blank")).toEqual({ kind: "blank" });
    expect(cellOf("achao.07")).toEqual({ kind: "emote", key: "achao.07" });
  });

  it("pays the symbol shown three times", () => {
    expect(outcomeOf(["skin", "5000", "skin", "again", "12500", "skin", "5000", "blank", "again"]))
      .toEqual({ kind: "skin", at: [0, 2, 5] });
    expect(outcomeOf(["blank", "5000", "blank", "again", "12500", "jackpot", "5000", "40000", "again"])).toEqual({ kind: "miss" });
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
    expect(levelOf(won("jackpot"), "basic")).toBe(3);
    expect(levelOf(won("skin"), "premium")).toBe(3);
    // a skin the save already had pays 30000, twelve times a premium card
    expect(levelOf(won("skin"), "premium", { tier: "skin", shards: 30000, coins: 0, item: null })).toBe(1);
    expect(levelOf(won("big"), "premium", { tier: "big", shards: 60000, coins: 0, item: null })).toBe(2);
    expect(levelOf(won("big"), "premium", { tier: "big", shards: 0, coins: 0, item: "card:c1" })).toBe(3);
  });

  it("gives 阿草 a cutout face for every result", () => {
    const faces = [faceOf({ kind: "miss" }, 0), faceOf(won("again"), "plain"), faceOf(won("1000"), 1),
      faceOf(won("8000"), 2), faceOf(won("jackpot"), 3), faceOf(won("achao.01"), 1)];
    for (const name of faces) expect(ACHAO[name], name).toMatch(/assets\/emotes\/achao\/\d\d\.webp$/);
  });
});

describe("odds", () => {
  it("lists the basic card best first and moves the emote tier to again once the set is whole", () => {
    expect(oddsRows("basic", false).map((r) => [r.kind, r.shards ?? null, r.rate])).toEqual([
      ["jackpot", null, "1/12000"], ["shards", 50000, "0.05%"], ["shards", 8000, "0.6%"], ["shards", 2500, "3.5%"],
      ["shards", 1000, "9.5%"], ["emote", null, "5%"], ["again", null, "15%"], ["miss", null, "66.3%"],
    ]);
    expect(oddsRows("basic", false).find((r) => r.kind === "emote")?.pity).toBe(10);
    expect(oddsRows("basic", true).map((r) => [r.kind, r.rate]).slice(-2)).toEqual([["again", "20%"], ["miss", "66.3%"]]);
  });

  it("lists the premium card with its skin and big hidden card", () => {
    expect(oddsRows("premium", false).map((r) => [r.kind, r.shards ?? null, r.rate])).toEqual([
      ["jackpot", null, "5/12000"], ["shards", 250000, "0.02%"], ["big", null, "0.1%"], ["shards", 40000, "0.5%"],
      ["skin", null, "0.2%"], ["shards", 12500, "3%"], ["shards", 5000, "13%"], ["again", null, "12%"], ["miss", null, "71.1%"],
    ]);
  });

  it("matches the bundled manifest", () => {
    expect(SCRATCH.cards.basic.coins).toBe(1);
    expect(SCRATCH.cards.premium.coins).toBe(5);
  });
});
