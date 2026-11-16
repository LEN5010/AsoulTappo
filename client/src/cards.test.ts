import { describe, expect, it } from "vitest";
import { albumCards, byTier, cardFrame, cardLabel, cardProgress, cardWord, holoId, ownsHolo, playsCardVideo, poolName } from "./cards";
import { manifest } from "./manifest";

describe("cardWord", () => {
  it("stamps hidden cards by tier and normal cards by what their video does", () => {
    const card = (tier: "big" | "small" | "normal", video: string | null, still = false) => ({ tier, video, still });
    expect(cardWord(card("big", "v.mp4"))).toBe("SECRET");
    expect(cardWord(card("small", "v.mp4", true))).toBe("HIDDEN");
    expect(cardWord(card("normal", "v.mp4"))).toBe("DANCE");
    expect(cardWord(card("normal", "v.mp4", true))).toBe("VOICE");
    expect(cardWord(card("normal", null))).toBe("NEW");
  });
  it("marks only video cards as still", () => {
    const still = manifest.cards.filter((c) => c.still);
    expect(still.map((c) => c.name)).toContain("海中密语");
    expect(still.every((c) => c.video)).toBe(true);
  });
});

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

describe("cardFrame", () => {
  it("frames big hidden cards in gold, small hidden and dance cards in coral", () => {
    expect(cardFrame({ tier: "big", rarity: "legendary" })).toBe("frame-gold");
    expect(cardFrame({ tier: "small", rarity: "epic" })).toBe("frame-rose");
    expect(cardFrame({ tier: "normal", rarity: "epic" })).toBe("frame-rose");
    expect(cardFrame({ tier: "normal", rarity: "limited" })).toBe("frame-pearl");
    expect(cardFrame({ tier: "normal", rarity: "common" })).toBe("");
    expect(cardFrame(undefined)).toBe("");
  });
});

describe("holo versions", () => {
  const holos = manifest.cards.filter((c) => c.holo);
  const plain = manifest.cards.find((c) => !c.holo)!;

  it("are 21 static normal cards, seven in each of the three series with official masks", () => {
    expect(holos).toHaveLength(21);
    const bySeries = Object.fromEntries(["moon", "casket", "reverie"].map((s) => [s, holos.filter((c) => c.series === s).length]));
    expect(bySeries).toEqual({ moon: 7, casket: 7, reverie: 7 });
    for (const c of holos) {
      expect(c.tier).toBe("normal");
      expect(c.video).toBeNull();
      expect(c.holo!.mask).toBe(`pack:holo/${c.id}.webp`);
      expect(c.holo!.since).toBe("1.2.4");
      for (const v of Object.values(c.holo!.shine)) expect(Number.isFinite(v)).toBe(true);
    }
  });

  it("are owned by their own item, not by the card", () => {
    const card = holos[0]!;
    expect(holoId(card)).toBe(`holo:${card.id}`);
    expect(ownsHolo(card, { [`card:${card.id}`]: 1 })).toBe(false);
    expect(ownsHolo(card, { [`holo:${card.id}`]: 1 })).toBe(true);
    expect(ownsHolo(plain, { [`holo:${plain.id}`]: 1 })).toBe(false);
  });

  it("count as cards of their own in the progress", () => {
    const card = holos[0]!;
    expect(cardProgress(manifest.cards, {})).toEqual([0, manifest.cards.length + 21]);
    expect(cardProgress([card], { [`card:${card.id}`]: 1 })).toEqual([1, 2]);
    expect(cardProgress([card], { [`card:${card.id}`]: 1, [`holo:${card.id}`]: 1 })).toEqual([2, 2]);
    expect(cardProgress([plain], { [`card:${plain.id}`]: 3 })).toEqual([1, 1]);
  });
});

describe("albumCards", () => {
  const holos = manifest.cards.filter((c) => c.holo);
  it("lists the 21 holo cards under 镭射, owned or not", () => {
    expect(albumCards(manifest.cards, "holo", {}).map((c) => c.id).sort()).toEqual(holos.map((c) => c.id).sort());
    const one = holos[3]!;
    expect(albumCards(manifest.cards, "holo", { [`holo:${one.id}`]: 1 })).toHaveLength(21);
  });

  it("filters by the card itself otherwise, hidden cards first", () => {
    const card = holos[0]!;
    // A holo version alone does not make the card owned.
    expect(albumCards(manifest.cards, "owned", { [`holo:${card.id}`]: 1 })).toEqual([]);
    expect(albumCards(manifest.cards, "owned", { [`card:${card.id}`]: 1 }).map((c) => c.id)).toEqual([card.id]);
    expect(albumCards(manifest.cards, "missing", { [`card:${card.id}`]: 1 })).toHaveLength(manifest.cards.length - 1);
    expect(albumCards(manifest.cards, "hidden", {}).every((c) => c.tier !== "normal")).toBe(true);
    const all = albumCards(manifest.cards, "all", {});
    expect(all).toHaveLength(manifest.cards.length);
    expect(all.map((c) => c.tier)).toEqual([...all].sort(byTier).map((c) => c.tier));
  });
});
