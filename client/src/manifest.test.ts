import { describe, expect, it } from "vitest";
import { buildSkin } from "./skin";
import { characterColor, getCard, getDecor, getEmote, getTheme, manifest, resolveAsset, skinTitle } from "./manifest";

describe("resolveAsset", () => {
  it("maps bundle: under the app base and pack: to the server", () => {
    expect(resolveAsset("bundle:cards/thumb/a.webp", "http://h:8000")).toBe("/assets/cards/thumb/a.webp");
    expect(resolveAsset("bundle:x.webp", "", "/app")).toBe("/app/assets/x.webp");
    expect(resolveAsset("pack:cards/s/a.mp4", "http://h:8000/")).toBe("http://h:8000/packs/cards/s/a.mp4");
    expect(resolveAsset("pack:cards/s/a.mp4", "")).toBe("");
    expect(resolveAsset(null, "")).toBe("");
    expect(resolveAsset("https://e/x.png", "")).toBe("https://e/x.png");
  });
});

describe("manifest", () => {
  it("only contains the five allowed characters", () => {
    expect(manifest.characters.map((c) => c.name)).toEqual(["嘉然", "乃琳", "贝拉", "心宜", "思诺"]);
    const ok = new Set(manifest.characters.map((c) => c.name));
    for (const c of manifest.cards) c.characters.forEach((n) => expect(ok.has(n)).toBe(true));
    // 阿草's set, won from scratch cards, is the one set that belongs to no member
    for (const s of manifest.emoteSets) expect(ok.has(s.character) || s.source === "scratch").toBe(true);
    expect(manifest.emoteSets.filter((s) => s.source).map((s) => s.id)).toEqual(["achao"]);
  });
  it("indexes work and ids are unique", () => {
    expect(new Set(manifest.cards.map((c) => c.id)).size).toBe(manifest.cards.length);
    expect(getCard(manifest.cards[0].id)).toBe(manifest.cards[0]);
    expect(getEmote(manifest.emoteSets[0].emotes[0].key)).toBeTruthy();
    expect(manifest.decor).toEqual([]);
    expect(manifest.accessories).toEqual([]);
    expect(manifest.cards).toHaveLength(85);
    expect(getDecor(null)).toBeUndefined();
    expect(characterColor("嘉然")).toBe("#e799b0");
    expect(characterColor("贝拉山海经")).toBe(characterColor("贝拉"));
    expect(characterColor("???")).toBe("#ff6b9d");
  });
  it("shows a skin by its title and anything else by its name", () => {
    expect(skinTitle("嘉然山海经")).toBe("嘉然帝江");
    expect(skinTitle("乃琳2025生日")).toBe("乃琳酒馆");
    expect(skinTitle("嘉然冬日奇迹")).toBe("嘉然冬日奇迹");
    expect(skinTitle("嘉然")).toBe("嘉然");
    expect(skinTitle("???")).toBe("???");
  });
  it("default theme is fully bundled; unknown ids fall back to it", () => {
    const d = getTheme(manifest.defaultTheme);
    expect(d.pack).toBeNull();
    expect(getTheme("nope").id).toBe(d.id);
    expect(Object.values(d.parts).flat().every((r) => (r as string).startsWith("bundle:"))).toBe(true);
  });
  it("lists 阿草's plate, unlocked by the scratch set, under an id no card has", () => {
    expect(manifest.plates).toEqual([{ id: "achao", name: "阿草", emoteSet: manifest.economy.scratch.emote.set }]);
    for (const p of manifest.plates) {
      expect(getCard(p.id)).toBeUndefined();
      expect(manifest.emoteSets.find((s) => s.id === p.emoteSet)?.emotes).toHaveLength(20);
    }
  });
  it("wire emote keys fit the server limit", () => {
    for (const s of manifest.emoteSets) for (const e of s.emotes) expect(e.key.length).toBeLessThanOrEqual(32);
  });
  it("ships every dynamic card video as a local client asset", () => {
    const videos = manifest.cards.flatMap((c) => c.video ? [c.video] : []);
    expect(videos).toHaveLength(33);
    for (const video of videos) {
      expect(video).toMatch(/^bundle:cards\/.+\.mp4$/);
      expect(resolveAsset(video, "http://room-server:8000")).toMatch(/^\/assets\/cards\//);
    }
  });
});

describe("skin", () => {
  it("follows the character and resolves the loading art", () => {
    const k = buildSkin(manifest.defaultTheme, "嘉然", "http://s");
    expect(k.vars["--char"]).toBe("#e799b0");
    expect(k.loading).toMatch(/^\/assets\/themes\//);
    const pk = buildSkin("nailin-queen", "乃琳", "http://s");
    expect(pk.loading).toMatch(/^http:\/\/s\/packs\/themes\/nailin-queen\//);
  });
});

it("ships manifest v4 skins for exactly the non-member character directories", () => {
  expect(manifest.version).toBe(4);
  const members = new Set(manifest.characters.map((m) => m.name));
  const dirs = Object.keys(import.meta.glob("./assets/characters/*/bgImage.webp"))
    .map((path) => path.split("/")[3]!).filter((name) => !members.has(name)).sort();
  expect(dirs).toEqual(manifest.skins.map((s) => s.name).sort());
  expect(Object.values(manifest.rarities).every((r) => Object.keys(r).join() === "name")).toBe(true);
});

describe("duel numbers", () => {
  it("are the approved ones, read from the manifest the server uses", () => {
    const duel = manifest.economy.duel!;
    expect(duel.stakes).toEqual([{ bet: 150, prize: 250 }, { bet: 1500, prize: 2500 }, { bet: 15000, prize: 25000 }]);
    expect([duel.inviteSec, duel.throwSec, duel.dailyWinCap, duel.minTaps]).toEqual([15, 10, 10000, 10000]);
  });
});
