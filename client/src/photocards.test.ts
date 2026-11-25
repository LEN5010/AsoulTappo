import { describe, expect, it } from "vitest";
import art from "./assets/photocards/asoul2026/cards.json";
import { items } from "./items";
import { manifest } from "./manifest";
import {
  isRarePhoto, isWidePhoto, photoItem, photoItems, photoItemsOf, photoOdds, photoPair, photoSeries, PHOTO_RARE_KINDS,
} from "./photocards";
import { exampleEconomy } from "./test/economy";

const CFG = exampleEconomy.photocards![0]!;
const all = photoItems(CFG.series);

it("lists the manifest's series in its order, each with a name, an event and cards", () => {
  expect(photoSeries.map((s) => s.id)).toEqual(manifest.photocards.map((s) => s.id));
  expect(photoSeries[0]).toMatchObject({ id: "asoul2026", name: "此间共鸣", event: "A-SOUL2026 线下演唱会" });
  for (const s of photoSeries) expect([!!s.name, !!s.event, photoItems(s.id).length > 0]).toEqual([true, true, true]);
});

describe("the photocards of a series", () => {
  it("lists solo, duo, group and signed cards in that order, under the server's ids", () => {
    expect([...new Set(all.map((i) => i.kind))]).toEqual(["solo", "duo", "group", "sign"]);
    expect([photoItemsOf(CFG.series, "solo").length, photoItemsOf(CFG.series, "duo").length,
      photoItemsOf(CFG.series, "group").length, photoItemsOf(CFG.series, "sign").length]).toEqual([12, 6, 4, 12]);
    expect(all[0]!.id).toBe("photo:asoul2026/diana-1");
    expect(photoItemsOf(CFG.series, "sign").map((i) => i.card))
      .toEqual(photoItemsOf(CFG.series, "solo").map((i) => i.card));
    expect(new Set(all.map((i) => i.id)).size).toBe(all.length);
    expect(all.every((i) => photoItem(i.id) === i)).toBe(true);
  });

  it("names members of the manifest", () => {
    const names = new Set(manifest.characters.map((c) => c.name));
    expect(all.every((i) => i.characters.length && i.characters.every((n) => names.has(n)))).toBe(true);
  });

  it("knows none of a series or item it lacks", () => {
    expect(photoItems("nope")).toEqual([]);
    expect(photoItem("photo:nope/diana-1")).toBeUndefined();
  });

  it("pairs a solo card with its signed version and nothing else", () => {
    const solo = photoItem("photo:asoul2026/bella-2")!;
    const sign = photoItem("sign:asoul2026/bella-2")!;
    expect(photoPair(solo)).toBe(sign);
    expect(photoPair(sign)).toBe(solo);
    for (const i of all.filter((i) => isWidePhoto(i))) expect(photoPair(i)).toBeUndefined();
  });

  it("tells the rare and the sideways cards", () => {
    expect(new Set(all.filter(isRarePhoto).map((i) => i.kind))).toEqual(new Set(PHOTO_RARE_KINDS));
    expect(new Set(all.filter(isWidePhoto).map((i) => i.kind))).toEqual(new Set(["duo", "group"]));
  });

  it("stays apart from the album's items", () => {
    const ids = new Set(items.map((i) => i.id));
    expect(all.some((i) => ids.has(i.id))).toBe(false);
  });
});

// Built by scripts/photocards.
describe("the pictures of a series", () => {
  const files = Object.keys(import.meta.glob("./assets/photocards/asoul2026/{front,back,mat,sign,thumb}/*.webp")).sort();
  const template = (card: string) => card.replace(/-\d+$/, "");
  const cards = all.filter((i) => i.kind !== "sign");
  const templates = art.templates as Record<string, { size: number[]; back: string }>;

  it("are a front for each card, a finish for each template and back, a signature for each member, and small ones", () => {
    const backs = new Set(Object.values(templates).map((t) => t.back));
    const want = [
      ...cards.flatMap((c) => [`front/${c.card}`, `thumb/${c.card}`]),
      ...Object.keys(templates).map((t) => `mat/front-${t}`),
      ...[...backs].flatMap((b) => [`back/${b}`, `mat/back-${b}`]),
      ...Object.keys(art.signs).flatMap((m) => [`sign/${m}`, `thumb/sign-${m}`]),
    ];
    expect(files).toEqual(want.map((p) => `./assets/photocards/asoul2026/${p}.webp`).sort());
    expect(new Set(cards.map((c) => template(c.card)))).toEqual(new Set(Object.keys(templates)));
    expect(new Set(photoItemsOf(CFG.series, "sign").map((c) => template(c.card))))
      .toEqual(new Set(Object.keys(art.signs)));
  });

  it("lie the way their cards do, and say who stands where when there is more than one", () => {
    const stand = art.stand as Record<string, string[]>;
    for (const c of cards) {
      const [w, h] = templates[template(c.card)]!.size as [number, number];
      expect(w > h).toBe(isWidePhoto(c));
      expect(stand[c.card]?.length ?? 1).toBe(c.characters.length);
    }
  });
});

describe("photoOdds", () => {
  it("counts the certain card of a box and splits by weight", () => {
    const odds = photoOdds({ ...CFG, size: 10, rare: 5, split: { duo: 50, group: 30, sign: 20 } });
    expect(odds.rare).toBeCloseTo((100 + 9 * 5) / 10);
    expect(odds.duo).toBeCloseTo(odds.rare * 0.5);
    expect(odds.group).toBeCloseTo(odds.rare * 0.3);
    expect(odds.sign).toBeCloseTo(odds.rare * 0.2);
  });

  it("takes weights that do not sum to 100", () => {
    const odds = photoOdds({ ...CFG, size: 20, rare: 0, split: { duo: 1, group: 0, sign: 3 } });
    expect([odds.rare, odds.duo, odds.group, odds.sign]).toEqual([5, 1.25, 0, 3.75]);
  });
});
