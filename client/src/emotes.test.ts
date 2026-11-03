import { describe, expect, it } from "vitest";
import { emoteGroups, emoteView, THUMBUP } from "./emotes";
import { manifest } from "./manifest";

const ctx = { serverBase: "http://s", thumbup: "/assets/t.webp", reducedMotion: false };

describe("emoteView", () => {
  it("resolves manifest emotes to images", () => {
    const key = manifest.emoteSets[0].emotes[0].key;
    expect(emoteView(key, ctx).img).toMatch(/^\/assets\/emotes\//);
  });
  it("thumbup uses the theme animation, or a glyph with reduced motion / no part", () => {
    expect(emoteView(THUMBUP, ctx)).toEqual({ img: "/assets/t.webp", animated: true });
    expect(emoteView(THUMBUP, { ...ctx, reducedMotion: true })).toEqual({ text: "👍" });
    expect(emoteView(THUMBUP, { ...ctx, thumbup: "" })).toEqual({ text: "👍" });
  });
  it("keeps legacy glyph keys and shows unknown keys as short text", () => {
    expect(emoteView("heart", ctx)).toEqual({ text: "❤️" });
    expect(emoteView("whatever-long", ctx)).toEqual({ text: "what" });
  });
});

describe("emoteGroups", () => {
  it("groups sets by character, covering every set", () => {
    const g = emoteGroups();
    expect(g.map((x) => x.character.name)).toEqual(["嘉然", "乃琳", "贝拉", "心宜", "思诺"]);
    expect(g.reduce((n, x) => n + x.sets.length, 0)).toBe(manifest.emoteSets.length);
  });
});
