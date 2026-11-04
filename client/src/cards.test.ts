import { describe, expect, it } from "vitest";
import { byTier, cardLabel, poolName, poolSkin } from "./cards";
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

describe("poolSkin", () => {
  it("keeps the group-wide pool on the brand palette", () => {
    expect(poolSkin("bloom")).toEqual({ accent: "#FC966E", tokens: {}, mascots: [] });
  });
  it("gives every member pool its own accent and two stickers", () => {
    const pools = manifest.series.map((s) => s.id).filter((id) => id !== "bloom");
    const accents = pools.map((id) => poolSkin(id).accent);
    expect(new Set(accents).size).toBe(pools.length);
    for (const id of pools) expect(poolSkin(id).mascots).toHaveLength(2);
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
