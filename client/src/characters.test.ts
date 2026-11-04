import { describe, expect, it } from "vitest";
import { characters, getCharacter, headAnchor } from "./characters";
import { starterEmotesOf } from "./items";

describe("skins", () => {
  it("take missing layers from the member", () => {
    const skin = characters["贝拉山海经"]!;
    const base = characters["贝拉"]!;
    expect(skin.bg).not.toBe(base.bg);
    expect([skin.keyboard, skin.mouse, skin.leftClick, skin.rightClick])
      .toEqual([base.keyboard, base.mouse, base.leftClick, base.rightClick]);
  });
  it("follow the member's head anchor and starter emotes", () => {
    expect(headAnchor("贝拉山海经")).toEqual(headAnchor("贝拉"));
    expect(starterEmotesOf("贝拉山海经")).toEqual(starterEmotesOf("贝拉"));
  });
  it("show the member when this client does not have the skin", () => {
    expect(getCharacter("思诺新皮肤")).toBe(characters["思诺"]);
  });
});
