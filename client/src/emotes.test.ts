import { describe, expect, it } from "vitest";
import { emoteGroups, emoteView } from "./emotes";
import { manifest } from "./manifest";

const ctx = { serverBase: "http://s" };

describe("emoteView", () => {
  it("resolves manifest emotes to images", () => {
    const key = manifest.emoteSets[0].emotes[0].key;
    expect(emoteView(key, ctx)?.img).toMatch(/^\/assets\/emotes\//);
  });
  it("shows nothing for unknown keys", () => {
    expect(emoteView("heart", ctx)).toBeNull();
    expect(emoteView("thumbup", ctx)).toBeNull();
    expect(emoteView("whatever-long", ctx)).toBeNull();
  });
});

describe("emoteGroups", () => {
  it("groups sets by character, covering every set", () => {
    const g = emoteGroups();
    expect(g.map((x) => x.character.name)).toEqual(["嘉然", "乃琳", "贝拉", "心宜", "思诺"]);
    expect(g.reduce((n, x) => n + x.sets.length, 0)).toBe(manifest.emoteSets.length);
  });
});
