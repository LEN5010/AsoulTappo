import { describe, expect, it } from "vitest";
import { byTier, cardLabel, playsCardVideo, poolName } from "./cards";
import { manifest } from "./manifest";

describe("poolName", () => {
  it("keeps only the distinguishing part", () => {
    expect(poolName("A-SOUL 绽放收藏集")).toBe("绽放");
    expect(poolName("嘉然的画册 · 绚烂心迹")).toBe("绚烂心迹");
    expect(poolName("心宜和思诺的交响乐谱 · 双声巡梦")).toBe("双声巡梦");
  });
  it("gives every pool a distinct short name", () => {
    const names = manifest.series.map((s) => poolName(s.name));
    expect(new Set(names).size).toBe(names.length);
    expect(Math.max(...names.map((n) => n.length))).toBeLessThanOrEqual(6);
  });
});

describe("cardLabel", () => {
  it("drops book marks that wrap the whole title", () => {
    expect(cardLabel({ name: "《Hopeful Dreamer》", characters: ["嘉然", "乃琳"] }).title).toBe("Hopeful Dreamer");
    expect(cardLabel({ name: "《绽放》舞蹈-贝拉", characters: ["贝拉"] }).title).toBe("《绽放》舞蹈");
  });
  it("splits the member off a series card", () => {
    expect(cardLabel({ name: "时序系列-嘉然", characters: ["嘉然"] })).toEqual({ title: "时序系列", who: "嘉然" });
    expect(cardLabel({ name: "《绽放》舞蹈-贝拉", characters: ["贝拉"] })).toEqual({ title: "《绽放》舞蹈", who: "贝拉" });
  });
  it("keeps other names whole", () => {
    expect(cardLabel({ name: "与你相依", characters: ["心宜", "思诺"] })).toEqual({ title: "与你相依", who: "心宜 · 思诺" });
    expect(cardLabel({ name: "A-B", characters: ["嘉然"] }).title).toBe("A-B");
  });
  it("tells every card of the largest pool apart", () => {
    const bloom = manifest.cards.filter((c) => c.series === "bloom").map(cardLabel).map((l) => `${l.title}/${l.who}`);
    expect(new Set(bloom).size).toBe(bloom.length);
  });
});

it("sorts the rarest tier first", () => {
  expect([{ tier: "normal" as const }, { tier: "big" as const }, { tier: "small" as const }].sort(byTier).map((c) => c.tier)).toEqual(["big", "small", "normal"]);
});

it("plays owned dynamic cards and shows static posters for every unowned card", () => {
  for (const tier of ["normal", "small", "big"] as const) {
    const card = { tier, video: "bundle:card.mp4" };
    expect(playsCardVideo(card, 0, false)).toBe(false);
    expect(playsCardVideo(card, undefined, false)).toBe(false);
    expect(playsCardVideo(card, 1, false)).toBe(true);
    expect(playsCardVideo(card, 1, true)).toBe(false);
  }
  expect(playsCardVideo({ video: null }, 1, false)).toBe(false);
});

it("plays resonance demo cards at every ownership level", () => {
  const card = { video: "bundle:card.mp4" };
  expect(playsCardVideo(card, 0, false, true)).toBe(true);
  expect(playsCardVideo(card, undefined, false, true)).toBe(true);
  expect(playsCardVideo(card, 0, true, true)).toBe(false);
});
