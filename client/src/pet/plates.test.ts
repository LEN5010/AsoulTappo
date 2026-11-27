import { describe, expect, it } from "vitest";
import { manifest } from "../manifest";
import {
  ACHAO_ARMS_MS, ACHAO_FACE_MS, ACHAO_FALL_MS, ACHAO_RISE_MS, BANNER_ASPECT, BANNER_EYES, BANNER_FIT, CARD_PAN, PAN_CYCLE_MS,
  PICTURE_ANCHOR, PICTURE_GAP, PLATE_ANCHOR, PLATE_CROPS, PLATE_MOTIONS, PLATE_PICTURES, PLATE_SWEEPS, allPlates, bannerArt,
  getPlate, motionArt, nameBand, panAt, panCycle, pictureArt, plateArt, plateCard, plateCards, plateMembers, plateNeeds,
  plateSet, plateSize, plateUnlocked, sweepArt, sweepFrames, videoFace,
} from "./plates";

describe("name plates", () => {
  it("covers every big hidden card and nothing else", () => {
    const big = manifest.cards.filter((c) => c.tier === "big").map((c) => c.id);
    expect(allPlates().filter((p) => p.kind === "card").map((p) => p.id)).toEqual(big);
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

describe("阿草's plate", () => {
  const owning = (items: string[]) => Object.fromEntries(items.map((i) => [i, 1]));
  const achao = () => getPlate("achao")!;

  it("comes from the manifest, after the cards, with a picture for every manifest plate", () => {
    expect(manifest.plates[0]).toEqual({ id: "achao", name: "阿草", emoteSet: "achao" });
    expect(allPlates().map((p) => p.id)).toEqual([...manifest.cards.filter((c) => c.tier === "big").map((c) => c.id), ...manifest.plates.map((p) => p.id)]);
    expect(Object.keys(PLATE_SWEEPS)).toEqual(manifest.plates.filter((p) => p.series === undefined).map((p) => p.id));
    expect(Object.keys(PLATE_MOTIONS)).toEqual(manifest.plates.filter((p) => p.series !== undefined && p.video).map((p) => p.id));
    expect(Object.keys(PLATE_PICTURES)).toEqual(manifest.plates.filter((p) => p.series !== undefined && !p.video).map((p) => p.id));
    expect(manifest.plates.some((p) => manifest.cards.some((c) => c.id === p.id))).toBe(false);
    const p = achao();
    expect(p).toMatchObject({ kind: "sweep", name: "阿草", set: "achao" });
    expect(plateCard("achao")).toBeNull();
    expect(plateNeeds(p)).toEqual(Array.from({ length: 20 }, (_, n) => `emote:achao.${String(n + 1).padStart(2, "0")}`));
  });

  it("unlocks with all twenty emotes", () => {
    const needs = plateNeeds(achao());
    expect(plateUnlocked("achao", {})).toBe(false);
    expect(plateUnlocked("achao", owning(needs.slice(1)))).toBe(false);
    expect(plateUnlocked("achao", owning(needs))).toBe(true);
    expect(plateUnlocked("nope", owning(needs))).toBe(false);
  });

  it("rests on the arms, rises for 4.5 s, rests on the face and drops back", () => {
    const r = PLATE_SWEEPS.achao!.rhythm;
    expect([ACHAO_ARMS_MS, ACHAO_RISE_MS, ACHAO_FACE_MS, ACHAO_FALL_MS]).toEqual([800, 4500, 6000, 1200]);
    expect(panCycle(r)).toBe(12500);
    expect(panAt(0, r)).toBe(0);
    expect(panAt(799, r)).toBe(0);
    expect(panAt(800 + 2250, r)).toBeCloseTo(0.5);
    expect(panAt(5300, r)).toBe(1);
    expect(panAt(11299, r)).toBe(1);
    expect(panAt(11300 + 600, r)).toBeCloseTo(0.5);
    expect(panAt(12500 + 6000, r)).toBe(1);
  });

  it("gives the animation the same stops as panAt", () => {
    for (const r of [PLATE_SWEEPS.achao!.rhythm, CARD_PAN]) {
      const frames = sweepFrames(r);
      expect(frames[0]!.offset).toBe(0);
      expect(frames.at(-1)!.offset).toBe(1);
      for (const f of frames.slice(1, -1)) expect(panAt(f.offset * panCycle(r) + 1e-6, r)).toBeCloseTo(f.p);
      expect(frames.map((f) => f.p)).toEqual([0, 0, 1, 1, 0]);
    }
  });

  it("frames the face at rest and the arms below it, on a picture of its own shape", () => {
    const sweep = PLATE_SWEEPS.achao!;
    const { face, from } = sweepArt(sweep, 224, 26);
    expect(face.height / face.width).toBeCloseTo(620 / 420);
    expect(face.width).toBeCloseTo(130); // narrower than the strip on purpose: coral shows at the left
    expect(face.top + sweep.face.fy * face.height).toBeCloseTo(13);
    expect(from.top + sweep.from.fy * from.height).toBeCloseTo(13);
    expect(from.top).toBeLessThan(face.top);
    expect(from.width).toBe(face.width);
  });

  it("keeps a picture narrower than the strip whole inside it, the eyes at the anchor", () => {
    const sweep = PLATE_SWEEPS.achao!;
    // the windows inside 228x30, 182x24, 160x21 and 342x40 plates
    for (const [w, h] of [[224, 26], [178, 20], [156, 17], [338, 36]] as const) {
      const { face } = sweepArt(sweep, w, h);
      expect(face.left + sweep.face.fx * face.width).toBeCloseTo(PLATE_ANCHOR * w);
      for (const art of Object.values(sweepArt(sweep, w, h))) {
        expect(art.width).toBeLessThan(w);
        expect(art.left).toBeGreaterThanOrEqual(0);
        expect(art.left + art.width).toBeLessThanOrEqual(w + 1e-9);
        expect(art.top).toBeLessThanOrEqual(0);
        expect(art.top + art.height).toBeGreaterThanOrEqual(h - 1e-9);
      }
    }
    // narrower than the strip and the eyes would sit past the anchor: it goes as far right as it can, not to the left
    const art = plateArt({ fx: 0.5, fy: 0.5, fw: 0.2 }, 338, 36, PLATE_ANCHOR, 1.5);
    expect(art.left).toBeCloseTo(338 - art.width);
  });
});

describe("the profile banner", () => {
  const w = 540, h = w / BANNER_ASPECT;
  it("draws each card exactly as wide as the banner, covering it, the eyes a little above the middle", () => {
    for (const plate of allPlates()) {
      if (plate.kind !== "card") continue;
      const art = bannerArt(plate.crop, w, h);
      expect(art.width).toBe(w);
      expect(art.left).toBe(0);
      expect(art.top).toBeLessThanOrEqual(0);
      expect(art.top + art.height).toBeGreaterThanOrEqual(h);
      const centre = plate.crop.bannerFy ?? plate.crop.fy;
      expect(art.top + centre * art.height).toBeCloseTo(BANNER_EYES * h);
    }
  });

  it("keeps both faces of 巡梦漫游 on the banner", () => {
    const plate = getPlate("c1748345610010")!;
    if (plate.kind !== "card") throw new Error("not a card plate");
    const art = bannerArt(plate.crop, w, h);
    // 思诺's eyes sit about 0.17 down the still, 心宜's at its crop's fy
    for (const fy of [0.17, plate.crop.fy]) {
      const y = art.top + fy * art.height;
      expect(y).toBeGreaterThan(0);
      expect(y).toBeLessThan(h);
    }
  });

  it("keeps 阿草's cut-out whole on its coral", () => {
    const boxes = sweepArt(PLATE_SWEEPS.achao!, w, h, BANNER_FIT);
    expect(boxes.face.width).toBeLessThan(w);
    expect(boxes.face.left).toBeGreaterThanOrEqual(0);
    expect(boxes.face.left + boxes.face.width).toBeLessThanOrEqual(w);
  });
});

describe("the 衣橱 plates", () => {
  const ids = ["wardrobe-jiaran", "wardrobe-nailin", "wardrobe-beila"];
  const series = () => ids.map((id) => {
    const p = getPlate(id)!;
    if (p.kind !== "series") throw new Error(`${id} is not a series plate`);
    return p;
  });

  it("are unlocked by the twelve cards of their member's series", () => {
    for (const [p, member] of series().map((p, i) => [p, ["嘉然", "乃琳", "贝拉"][i]!] as const)) {
      expect(plateMembers(p)).toEqual([member]);
      const cards = manifest.cards.filter((c) => c.series === p.series);
      expect(cards).toHaveLength(12);
      expect(plateCards(p)).toEqual(cards);
      expect(plateNeeds(p)).toEqual(cards.map((c) => `card:${c.id}`));
      expect(plateCard(p.id)).toBeNull();
      const owned = Object.fromEntries(plateNeeds(p).map((i) => [i, 1]));
      expect(plateUnlocked(p.id, owned)).toBe(true);
      delete owned[plateNeeds(p).at(-1)!];
      expect(plateUnlocked(p.id, owned)).toBe(false);
    }
  });

  it("cover the strip, leaving bare at most their gap at the left", () => {
    for (const p of series()) {
      for (const [w, h] of [[224, 26], [116, 20], [336, 36], [87, 12], [452, 36]] as const) {
        const art = motionArt(p, w, h);
        expect(art.left).toBeLessThanOrEqual((p.motion.gap ?? 0) * w + 1e-9);
        expect(art.left + art.width).toBeGreaterThanOrEqual(w - 1e-9);
        expect(art.top).toBeLessThanOrEqual(1e-9);
        expect(art.top + art.height).toBeGreaterThanOrEqual(h - 1e-9);
      }
    }
    // 贝拉 sits left in her video: the gap brings her eyes over to the anchor, bare strip under the nickname.
    const beila = series()[2]!, art = motionArt(beila, 224, 26);
    expect(art.left).toBeGreaterThan(0);
    expect(art.left + beila.motion.face.fx * art.width).toBeCloseTo(PLATE_ANCHOR * 224);
  });

  it("cover the profile banner, even a narrow one", () => {
    for (const p of series()) {
      for (const w of [540, 120]) {
        const h = 184, art = bannerArt(p.motion.face, w, h, p.aspect);
        expect(art.left).toBe(0);
        expect(art.width).toBeGreaterThanOrEqual(w);
        expect(art.top).toBeLessThanOrEqual(0);
        expect(art.top + art.height).toBeGreaterThanOrEqual(h - 1e-9);
      }
    }
  });
});

describe("the 脑洞波 plates", () => {
  const members = { "naodong-jiaran": "嘉然", "naodong-nailin": "乃琳", "naodong-beila": "贝拉" } as const;
  const pictures = () => Object.keys(members).map((id) => {
    const p = getPlate(id)!;
    if (p.kind !== "picture") throw new Error(`${id} is not a picture plate`);
    return p;
  });
  // the windows inside plates under pets at x0.4, x0.6, x0.8, x1, x1.5 and x2
  const STRIPS = [[87, 12], [133, 14], [178, 20], [224, 26], [338, 36], [452, 36]] as const;

  it("are unlocked by the four cards of their member in the series, the other members' not counting", () => {
    for (const p of pictures()) {
      const member = members[p.id as keyof typeof members];
      expect(p).toMatchObject({ series: "naodong", member });
      expect(plateMembers(p)).toEqual([member]);
      const cards = manifest.cards.filter((c) => c.series === "naodong" && c.characters.join() === member);
      expect(cards).toHaveLength(4);
      expect(plateCards(p)).toEqual(cards);
      expect(plateNeeds(p)).toEqual(cards.map((c) => `card:${c.id}`));
      expect(plateCard(p.id)).toBeNull();
      const others = manifest.cards.filter((c) => c.series === "naodong" && c.characters.join() !== member);
      const owned = Object.fromEntries([...cards.slice(1), ...others].map((c) => [`card:${c.id}`, 1]));
      expect(plateUnlocked(p.id, owned)).toBe(false);
      owned[`card:${cards[0]!.id}`] = 1;
      expect(plateUnlocked(p.id, owned)).toBe(true);
    }
  });

  it("cover the right of the strip, leaving bare at most their gap at the left", () => {
    for (const p of pictures()) {
      for (const [w, h] of STRIPS) {
        const art = pictureArt(p, w, h);
        expect(art.left).toBeLessThanOrEqual(PICTURE_GAP * w + 1e-9);
        expect(art.left + art.width).toBeGreaterThanOrEqual(w - 1e-9);
        expect(art.top).toBeLessThanOrEqual(1e-9);
        expect(art.top + art.height).toBeGreaterThanOrEqual(h - 1e-9);
        expect(art.height / art.width).toBeCloseTo(p.aspect);
      }
    }
  });

  it("put the eyes right of the other plates', at their own anchor and mid-height", () => {
    expect(PICTURE_ANCHOR).toBeGreaterThan(PLATE_ANCHOR);
    for (const p of pictures()) {
      for (const [w, h] of STRIPS) {
        const art = pictureArt(p, w, h);
        expect(art.left + p.picture.face.fx * art.width).toBeCloseTo(PICTURE_ANCHOR * w);
        expect(art.top + p.picture.face.fy * art.height).toBeCloseTo(h / 2);
      }
    }
  });

  it("draw the face as large as the other plates do under a pet at x1, larger where the strip is long for its height", () => {
    for (const p of pictures()) {
      expect(pictureArt(p, 224, 26).width * p.picture.face.fw).toBeCloseTo(1.7 * 26);
      for (const [w, h] of STRIPS) expect(pictureArt(p, w, h).width * p.picture.face.fw).toBeGreaterThanOrEqual(1.7 * h - 1e-9);
    }
    // under a pet at x2 the strip is 12.6 times as long as it is high, against 8.6 at x1
    const beila = pictures()[2]!;
    expect(pictureArt(beila, 452, 36).width * beila.picture.face.fw / 36).toBeCloseTo(2.45, 1);
  });

  it("cover the profile banner, even a narrow one", () => {
    for (const p of pictures()) {
      for (const w of [540, 120]) {
        const h = 184, art = bannerArt(p.picture.face, w, h, p.aspect);
        expect(art.left).toBe(0);
        expect(art.width).toBeGreaterThanOrEqual(w);
        expect(art.top).toBeLessThanOrEqual(0);
        expect(art.top + art.height).toBeGreaterThanOrEqual(h - 1e-9);
      }
    }
  });

  it("are listed after the 衣橱 plates and are not 衣橱", () => {
    const ids = allPlates().map((p) => p.id);
    expect(ids.slice(-6)).toEqual(["wardrobe-jiaran", "wardrobe-nailin", "wardrobe-beila", ...Object.keys(members)]);
    expect(allPlates().filter((p) => p.kind === "series").map((p) => p.id)).toEqual(["wardrobe-jiaran", "wardrobe-nailin", "wardrobe-beila"]);
  });
});
