import { describe, expect, it } from "vitest";
import { collectionProgress } from "./items";
import { manifest } from "./manifest";

describe("collection progress", () => {
  const emotes = manifest.emoteSets.flatMap((s) => s.emotes);
  it("counts starter emotes as owned, as the album does", () => {
    expect(collectionProgress({})).toEqual({
      cards: [0, manifest.cards.length],
      emotes: [manifest.starter.emotes.length, emotes.length],
      skins: [0, manifest.skins.length],
    });
  });

  it("counts each owned card, emote and skin once", () => {
    const card = manifest.cards[0]!, skin = manifest.skins[0]!;
    const extra = emotes.find((e) => !manifest.starter.emotes.includes(e.key))!;
    const owned = { [`card:${card.id}`]: 3, [`char:${skin.name}`]: 1, [`emote:${extra.key}`]: 1, [`emote:${manifest.starter.emotes[0]}`]: 1 };
    const p = collectionProgress(owned);
    expect(p.cards[0]).toBe(1);
    expect(p.skins[0]).toBe(1);
    expect(p.emotes[0]).toBe(manifest.starter.emotes.length + 1);
  });
});
