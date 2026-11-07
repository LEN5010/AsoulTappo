import { describe, expect, it } from "vitest";
import { manifest } from "../manifest";
import { PAN_CYCLE_MS, PLATE_ANCHOR, PLATE_CROPS, panAt, plateArt, plateCard, plateCards, plateSize, videoFace } from "./plates";

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
      for (const [w, h] of [[224, 26], [116, 20], [336, 36]] as const) {
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
    expect(plateSize(0.4)).toEqual({ width: 120, height: 24 });
    expect(plateSize(1.5)).toEqual({ width: 342, height: 40 });
  });
});
