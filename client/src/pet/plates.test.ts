import { describe, expect, it } from "vitest";
import { manifest } from "../manifest";
import {
  PAN_CYCLE_MS, PLATE_ANCHOR, PLATE_CROPS, nameBand, panAt, plateArt, plateCard, plateCards, plateSet, plateSize,
  plateUnlocked, videoFace,
} from "./plates";

describe("name plates", () => {
  it("covers every big hidden card and nothing else", () => {
    const big = manifest.cards.filter((c) => c.tier === "big").map((c) => c.id);
    expect(plateCards().map((c) => c.id)).toEqual(big);
    expect(Object.keys(PLATE_CROPS).sort()).toEqual([...big].sort());
    const normal = manifest.cards.find((c) => c.tier !== "big")!;
    expect(plateCard(normal.id)).toBeNull();
    expect(plateCard("nope")).toBeNull();
    expect(plateCard("")).toBeNull();
    expect(plateCard(null)).toBeNull();
  });

  it("puts the eyes at the anchor and mid-height when the card has room", () => {
    const art = plateArt({ fx: 0.5, fy: 0.5, fw: 0.1 }, 224, 26);
    expect(art.left + 0.5 * art.width).toBeCloseTo(PLATE_ANCHOR * 224);
    expect(art.top + 0.5 * art.height).toBeCloseTo(13);
  });

  it("never shows past the card's edges", () => {
    for (const crop of Object.values(PLATE_CROPS)) {
      for (const [w, h] of [[224, 26], [116, 20], [336, 36], [87, 12]] as const) {
        for (const face of [crop, videoFace(crop, 0), videoFace(crop, PAN_CYCLE_MS / 2)]) {
          const art = plateArt(face, w, h);
          expect(art.left).toBeLessThanOrEqual(0);
          expect(art.top).toBeLessThanOrEqual(0);
          expect(art.left + art.width).toBeGreaterThanOrEqual(w - 1e-9);
          expect(art.top + art.height).toBeGreaterThanOrEqual(h - 1e-9);
        }
      }
    }
  });

  it("holds on each face and glides between them", () => {
    expect(panAt(0)).toBe(0);
    expect(panAt(3400)).toBe(0);
    expect(panAt(4250)).toBeCloseTo(0.5);
    expect(panAt(6000)).toBe(1);
    expect(panAt(9250)).toBeCloseTo(0.5);
    expect(panAt(PAN_CYCLE_MS + 6000)).toBe(1);
  });

  it("follows the video crop and the pan", () => {
    const still = { fx: 0.4, fy: 0.3, fw: 0.1 };
    expect(videoFace({ ...still, video: { fy: 0.2 } }, 0)).toEqual({ ...still, fy: 0.2 });
    const duo = { ...still, pan: [{ fx: 0.4, fy: 0.25 }, { fx: 0.6, fy: 0.1 }] } as const;
    expect(videoFace(duo, 0)).toEqual({ fx: 0.4, fy: 0.25, fw: 0.1 });
    expect(videoFace(duo, 6000)).toEqual({ fx: 0.6, fy: 0.1, fw: 0.1 });
  });

  it("scales with partners' pets within bounds", () => {
    expect(plateSize(1)).toEqual({ width: 228, height: 30 });
    expect(plateSize(0.8)).toEqual({ width: 182, height: 24 });
    expect(plateSize(0.6)).toEqual({ width: 137, height: 18 });
    expect(plateSize(0.4)).toEqual({ width: 91, height: 16 });
    expect(plateSize(1.5)).toEqual({ width: 342, height: 40 });
  });

  it("keeps the nickname full size down to 0.8 and shrinks it below, within a floor", () => {
    expect(nameBand(1.5)).toEqual({ font: 12, pill: 22 });
    expect(nameBand(0.8)).toEqual({ font: 12, pill: 22 });
    expect(nameBand(0.6)).toEqual({ font: 10, pill: 16 });
    expect(nameBand(0.4)).toEqual({ font: 10, pill: 16 });
  });
});

describe("plate sets", () => {
  const byName = (name: string) => manifest.cards.find((c) => c.name === name)!;
  const owning = (cards: { id: string }[]) => Object.fromEntries(cards.map((c) => [`card:${c.id}`, 1]));

  it("asks for the plate member's cards in a shared collection and the whole duo collection", () => {
    const jiaran = plateSet(byName("时序系列-嘉然"));
    expect(jiaran).toHaveLength(7);
    expect(jiaran[0]!.name).toBe("时序系列-嘉然");
    expect(jiaran.every((c) => c.characters.join() === "嘉然")).toBe(true);
    expect(plateSet(byName("巡梦漫游"))).toHaveLength(10);
    expect(plateSet(byName("蝶影共醉"))).toHaveLength(9);
  });

  it("unlocks only with the whole set", () => {
    const card = byName("蝶影共醉");
    const set = plateSet(card);
    expect(plateUnlocked(card.id, owning([card]))).toBe(false);
    expect(plateUnlocked(card.id, owning(set.slice(1)))).toBe(false);
    expect(plateUnlocked(card.id, owning(set))).toBe(true);
    expect(plateUnlocked(set[1]!.id, owning(set))).toBe(false);
  });
});
