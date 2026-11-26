import { describe, expect, it } from "vitest";
import { manifest } from "../manifest";
import { OPEN_ART, seriesArt, type CardInfo } from "./art";

const all = manifest.photocards.flatMap((s) => {
  const art = seriesArt(s.id);
  return art ? [{ series: s, art }] : [];
});
const picture = (url: unknown) => expect(url).toMatch(/\.webp|^data:image\/webp/);

describe("the art of the photocards", () => {
  it("is there for the first series and for no other name", () => {
    expect(all.map((a) => a.art.id)).toContain("asoul2026");
    expect(seriesArt("nope")).toBeNull();
    expect(seriesArt("asoul2026")).toBe(seriesArt("asoul2026"));
    expect(seriesArt("asoul2026")!.stage).not.toBeNull();
  });

  it("has the pictures every series shares", () => {
    for (const url of Object.values(OPEN_ART)) picture(url);
  });
});

describe.each(all)("the art of $series.id", ({ series, art }) => {
  it("has a front, a mat and a back for every card, in the manifest's order", () => {
    expect(art.cards.map((c) => [c.id, c.kind])).toEqual(series.cards.map((c) => [c.id, c.kind]));
    for (const c of art.cards) {
      for (const url of [...c.front, ...c.behind]) picture(url);
      expect(new Set([...c.front, ...c.behind]).size).toBe(4);
      expect(art.card(c.id)).toBe(c);
    }
    expect(new Set(art.cards.map((c) => c.front[0])).size).toBe(art.cards.length);
  });

  it("has a signature for every solo card and for no other", () => {
    for (const c of art.cards) {
      const signed = art.signed(c.id);
      if (c.kind !== "solo") {
        expect(signed).toBeUndefined();
        continue;
      }
      const { signed: sign, ...rest } = signed!;
      picture(sign!.url);
      expect(sign!.member).toBe(c.stand[0]);
      expect(sign!.ms).toBeGreaterThan(0);
      expect(sign!.tip.length).toBeGreaterThan(1);
      sign!.uv.forEach((v, i) => expect(v * c.size[i % 2]).toBeCloseTo(sign!.box[i]));
      expect(rest).toEqual({ ...c, tones: rest.tones, light: rest.light });
    }
  });

  it("has a colour for everyone on a card, and light of those colours; a signed card's light is one of its own", () => {
    const bright = (list: CardInfo["light"]) => list.every((t) => Math.max(...t) === 1 && t.every((v) => v > 0));
    for (const c of art.cards) {
      expect(c.stand.length).toBe(c.characters.length);
      expect(c.tones.length).toBe(c.stand.length);
      expect(c.tones.every((t) => t.length === 3)).toBe(true);
      expect(c.light.length).toBe(c.tones.length);
      expect(bright(c.light)).toBe(true);
      const signed = art.signed(c.id);
      if (!signed) continue;
      expect(signed.tones).toEqual([signed.tones[0], ...c.tones]);
      expect(signed.light.length).toBe(1);
      expect(bright(signed.light)).toBe(true);
      expect(signed.light[0]).not.toEqual(c.light[0]);
    }
  });

  it("has a whole stage or none", () => {
    if (!art.stage) return;
    const { focus, depth, title, look } = art.stage;
    for (const url of [...focus, depth, title]) picture(url);
    expect(new Set([...focus, depth, title]).size).toBe(focus.length + 2);
    expect(focus.length).toBeGreaterThan(2);
    for (const c of [look.dark, look.mist, look.light, ...look.ground]) {
      expect(c.length).toBe(3);
      expect(c.every((v) => v >= 0 && v <= 1)).toBe(true);
    }
    expect(look.ground.length).toBe(2);
    expect(look.lamps.length).toBe(3);
    for (const at of look.lamps) expect(at.every((v) => v > 0 && v < 1)).toBe(true);
  });

  it("lays cards of several on their side", () => {
    for (const c of art.cards) {
      expect(c.land).toBe(c.kind !== "solo");
      expect(Math.min(...c.size)).toBe(1080);
    }
  });
});
