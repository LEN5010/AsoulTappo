import { describe, expect, it } from "vitest";
import { backgroundFor, buildSkin, hexToRgb, isDark } from "./skin";
import { characterColor, getCard, getDecor, getEmote, getTheme, manifest, resolveAsset } from "./manifest";

describe("resolveAsset", () => {
  it("maps bundle: under the app base and pack: to the server", () => {
    expect(resolveAsset("bundle:cards/thumb/a.webp", "http://h:8000")).toBe("/assets/cards/thumb/a.webp");
    expect(resolveAsset("bundle:x.webp", "", "/app")).toBe("/app/assets/x.webp");
    expect(resolveAsset("pack:cards/s/a.mp4", "http://h:8000/")).toBe("http://h:8000/packs/cards/s/a.mp4");
    expect(resolveAsset(null, "")).toBe("");
    expect(resolveAsset("https://e/x.png", "")).toBe("https://e/x.png");
  });
});

describe("manifest", () => {
  it("only contains the five allowed characters", () => {
    expect(manifest.characters.map((c) => c.name)).toEqual(["嘉然", "乃琳", "贝拉", "心宜", "思诺"]);
    const ok = new Set(manifest.characters.map((c) => c.name));
    for (const c of manifest.cards) c.characters.forEach((n) => expect(ok.has(n)).toBe(true));
    for (const s of manifest.emoteSets) expect(ok.has(s.character)).toBe(true);
  });
  it("indexes work and ids are unique", () => {
    expect(new Set(manifest.cards.map((c) => c.id)).size).toBe(manifest.cards.length);
    expect(getCard(manifest.cards[0].id)).toBe(manifest.cards[0]);
    expect(getEmote(manifest.emoteSets[0].emotes[0].key)).toBeTruthy();
    expect(getDecor(manifest.decor[0].id)).toBeTruthy();
    expect(getDecor(null)).toBeUndefined();
    expect(characterColor("嘉然")).toBe("#e799b0");
    expect(characterColor("???")).toBe("#ff6b9d");
  });
  it("default theme is fully bundled; unknown ids fall back to it", () => {
    const d = getTheme(manifest.defaultTheme);
    expect(d.pack).toBeNull();
    expect(getTheme("nope").id).toBe(d.id);
    expect(Object.values(d.parts).flat().every((r) => (r as string).startsWith("bundle:"))).toBe(true);
  });
  it("wire emote keys fit the server limit", () => {
    for (const s of manifest.emoteSets) for (const e of s.emotes) expect(e.key.length).toBeLessThanOrEqual(32);
  });
});

describe("skin", () => {
  it("builds css vars and urls from a theme", () => {
    const k = buildSkin(manifest.defaultTheme, "嘉然", "http://s");
    expect(k.vars["--accent"]).toMatch(/^#/);
    expect(k.vars["--char"]).toBe("#e799b0");
    expect(k.headBg).toMatch(/^\/assets\/themes\//);
    expect(k.icons.main.s).toContain("main_sel");
    const pk = buildSkin("nailin-queen", "乃琳", "http://s");
    expect(pk.headBg).toMatch(/^http:\/\/s\/packs\/themes\/nailin-queen\//);
  });
  it("cycles backgrounds and copes with none", () => {
    expect(backgroundFor({ backgrounds: ["a", "b", "c"] }, 4)).toBe("b");
    expect(backgroundFor({ backgrounds: ["a"] }, -3)).toBe("a");
    expect(backgroundFor({ backgrounds: [] }, 1)).toBe("");
  });
  it("color helpers", () => {
    expect(hexToRgb("#ff0080")).toBe("255, 0, 128");
    expect(hexToRgb("bad")).toBe("255, 107, 157");
    expect(isDark("#102030")).toBe(true);
    expect(isDark("#f0f0f0")).toBe(false);
  });
});
