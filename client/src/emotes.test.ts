import { describe, expect, it } from "vitest";
import { emoteView } from "./emotes";
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
