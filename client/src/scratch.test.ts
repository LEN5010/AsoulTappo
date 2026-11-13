import { describe, expect, it } from "vitest";
import { ACHAO } from "./ui/achao";
import { craftCost, getItem } from "./items";
import { manifest } from "./manifest";
import { poolOf } from "./resonance";
import { Coating, HOST, SCRATCH_EMOTES, cellOf, faceKey, faceOf, oddsRows, outcomeOf, ownedScratchEmotes, toneOf } from "./scratch";

const shards = (amount: number) => ({ kind: "shards" as const, amount, at: [0, 1, 2] });

describe("cards", () => {
  it("reads amounts and emotes", () => {
    expect(cellOf("2500")).toEqual({ kind: "shards", amount: 2500 });
    expect(cellOf("achao.07")).toEqual({ kind: "emote", key: "achao.07" });
  });

  it("pays the symbol shown three times and says where", () => {
    expect(outcomeOf(["200", "500", "200", "achao.01", "1000", "200", "500", "achao.01", "1000"]))
      .toEqual({ kind: "shards", amount: 200, at: [0, 2, 5] });
    expect(outcomeOf(["achao.03", "500", "200", "achao.03", "1000", "200", "500", "achao.03", "1000"]))
      .toEqual({ kind: "emote", key: "achao.03", at: [0, 3, 7] });
  });

  it("misses when nothing shows three times", () => {
    expect(outcomeOf(["200", "500", "200", "achao.01", "1000", "30000", "500", "achao.01", "30000"])).toEqual({ kind: "miss" });
  });
});

describe("阿草", () => {
  it("takes bigger prizes worse, with cutout stickers only", () => {
    const faces = [faceOf({ kind: "miss" }), ...manifest.economy.scratch.prizes.map((p) => faceOf(shards(p.shards)))];
    expect(faces).toEqual(["比心", "肯定", "收到", "流汗", "惊恐", "生无可恋"]);
    expect(faceOf({ kind: "emote", key: "achao.01", at: [0, 1, 2] })).toBe("对不起");
    // an amount between two prizes takes the face of the one below it
    expect(faceOf(shards(1200))).toBe("流汗");
    for (const name of [...faces, ...Object.values(HOST)]) {
      expect(ACHAO[name], name).toMatch(/assets\/emotes\/achao\/\d\d\.webp$/);
      expect(["微笑", "谢谢观看", "才八点", "晚安"]).not.toContain(name);
    }
  });

  it("keeps every sticker under its name", () => {
    expect(Object.keys(ACHAO)).toHaveLength(20);
    expect(ACHAO["拒绝"]).toBe("/assets/emotes/achao/08.webp");
    expect(faceKey("惊恐")).toBe("achao.05");
    expect(faceKey("nobody")).toBeUndefined();
  });

  it("tones wins like the check-in calendar", () => {
    expect([200, 500, 1000, 2500, 30000].map((n) => toneOf(shards(n))))
      .toEqual(["tone-rare", "tone-rare", "tone-rare", "tone-epic", "tone-legendary"]);
    expect(toneOf({ kind: "miss" })).toBe("");
    expect(toneOf({ kind: "emote", key: "achao.01", at: [] })).toBe("tone-epic");
  });
});

describe("odds", () => {
  it("lists the approved table and adds up to 100", () => {
    const rows = oddsRows(false);
    expect(rows.map((r) => [r.kind, r.shards, r.rate, r.pity])).toEqual([
      ["emote", null, 5, 10], ["shards", 30000, 0.1, undefined], ["shards", 2500, 3, undefined],
      ["shards", 1000, 8, undefined], ["shards", 500, 20, undefined], ["shards", 200, 25, undefined],
      ["miss", null, 38.9, undefined],
    ]);
    expect(rows.reduce((n, r) => n + r.rate, 0)).toBeCloseTo(100);
  });

  it("drops the emote tier into the miss once the set is whole", () => {
    const rows = oddsRows(true);
    expect(rows.map((r) => [r.kind, r.shards, r.rate, r.pity])).toEqual([
      ["shards", 30000, 0.1, undefined], ["shards", 2500, 3, undefined], ["shards", 1000, 8, undefined],
      ["shards", 500, 20, undefined], ["shards", 200, 25, undefined], ["miss", null, 43.9, undefined],
    ]);
    expect(rows.reduce((n, r) => n + r.rate, 0)).toBeCloseTo(100);
  });
});

describe("the scratch emote set", () => {
  it("is twenty emotes that are neither drawn nor crafted", () => {
    expect(SCRATCH_EMOTES).toHaveLength(20);
    const pool = Object.values(poolOf()).flat();
    expect(pool.some((item) => item.source || item.id.startsWith("emote:achao."))).toBe(false);
    // the pool is what it was before the set existed
    expect(pool).toHaveLength(552);
    const item = getItem("emote:achao.01")!;
    expect(item).toMatchObject({ kind: "emote", name: "兜风", source: "scratch", starter: false });
    expect(craftCost(item)).toBeNull();
  });

  it("counts what a save owns", () => {
    expect(ownedScratchEmotes({ "emote:achao.02": 1, "emote:jiaran-eat.05": 1, "emote:achao.20": 1 })).toEqual(["achao.02", "achao.20"]);
  });
});

describe("the coating", () => {
  it("starts whole and clears along a stroke", () => {
    const coating = new Coating(20);
    expect(coating.share).toBe(0);
    const one = coating.stroke(0.1, 0.5, 0.9, 0.5, 0.075);
    // a band 0.15 tall across 0.8 of the width, measured on a coarse grid
    expect(one).toBeGreaterThan(0.05);
    expect(one).toBeLessThan(0.2);
    // the same stroke again clears nothing more
    expect(coating.stroke(0.1, 0.5, 0.9, 0.5, 0.075)).toBe(one);
  });

  it("leaves no gap in a fast stroke and reaches the whole card", () => {
    const coating = new Coating(20);
    for (let y = 0.05; y <= 1; y += 0.1) coating.stroke(0, y, 1, y, 0.075);
    expect(coating.share).toBe(1);
  });

  it("tells how far the least scratched box is uncovered", () => {
    const left = { x0: 0, y0: 0, x1: 0.5, y1: 1 };
    const right = { x0: 0.5, y0: 0, x1: 1, y1: 1 };
    const coating = new Coating(40, [left, right]);
    expect(coating.least).toBe(0);
    for (let y = 0.05; y <= 1; y += 0.1) coating.stroke(0, y, 0.4, y, 0.075);
    // Half the card is gone, but the right box is still covered.
    expect(coating.share).toBeGreaterThan(0.4);
    expect(coating.least).toBe(0);
    for (let y = 0.05; y <= 1; y += 0.1) coating.stroke(0.55, y, 1, y, 0.075);
    expect(coating.least).toBe(1);
    expect(new Coating(20).least).toBe(0);
  });

  it("ignores strokes outside the card", () => {
    const coating = new Coating(20);
    expect(coating.stroke(-0.5, -0.5, -0.3, -0.3, 0.075)).toBe(0);
    expect(coating.stroke(0.5, 0.5, 0.5, 0.5, 0.075)).toBeGreaterThan(0);
  });
});
