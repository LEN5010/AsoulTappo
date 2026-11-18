import { describe, expect, it } from "vitest";
import { characters, formReach, getCharacter, headAnchor, PET_BASE } from "./characters";
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
  it.each([["贝拉2025生日", "贝拉"], ["嘉然2025生日", "嘉然"], ["乃琳2025生日", "乃琳"]])("ships %s with previews and %s's input layers", (name, member) => {
    const skin = characters[name]!;
    const base = characters[member]!;
    expect(getCharacter(skin.name)).toBe(skin);
    expect(skin.bg).not.toBe(base.bg);
    expect(skin.bgSmall).not.toBe(skin.bg);
    expect(skin.bgMedium).not.toBe(skin.bg);
    expect(skin.portrait).toBeTruthy();
    expect([skin.keyboard, skin.mouse, skin.leftClick, skin.rightClick])
      .toEqual([base.keyboard, base.mouse, base.leftClick, base.rightClick]);
  });
});

describe("two-form skins", () => {
  it.each([["嘉然然龙", "嘉然"], ["乃琳法师", "乃琳"], ["贝拉炎头队长", "贝拉"]])("ship %s with both pictures and %s's input layers", (name, member) => {
    const skin = characters[name]!;
    const base = characters[member]!;
    expect(skin.form).toBeTruthy();
    expect(skin.form!.bg).not.toBe(skin.bg);
    expect(skin.form!.bgSmall).not.toBe(skin.form!.bg);
    expect(skin.form!.bgMedium).not.toBe(skin.form!.bg);
    expect(skin.portrait).toBeTruthy();
    expect([skin.keyboard, skin.mouse, skin.leftClick, skin.rightClick])
      .toEqual([base.keyboard, base.mouse, base.leftClick, base.rightClick]);
  });
  it("are the only skins with a second picture", () => {
    expect(Object.values(characters).filter((c) => c.form).map((c) => c.name).sort())
      .toEqual(["乃琳法师", "嘉然然龙", "贝拉炎头队长"].sort());
  });
  it("are the only skins with a moving part", () => {
    expect(Object.values(characters).filter((c) => c.form?.loop).map((c) => c.name).sort())
      .toEqual(["乃琳法师", "嘉然然龙", "贝拉炎头队长"].sort());
  });
  // A loop may reach past the top (贝拉炎头队长's flame) or the right edge (嘉然然龙's open wing) of the picture; the
  // pet draws it outside its box.
  it("draw the armillary behind the figure and the artist-clipped wings and flame over it", () => {
    expect(Object.values(characters).filter((c) => c.form?.loop?.behind).map((c) => c.name).sort())
      .toEqual(["乃琳法师"]);
  });
  it("summon only 乃琳法师's armillary; the others fade in", () => {
    expect(Object.values(characters).filter((c) => c.form?.loop?.entrance).map((c) => [c.name, c.form!.loop!.entrance]))
      .toEqual([["乃琳法师", "summon"]]);
  });

  it.each(["贝拉炎头队长", "乃琳法师", "嘉然然龙"])("loop the moving part of %s over its second picture", (name) => {
    const loop = characters[name]!.form!.loop!;
    expect(loop.src).toBeTruthy();
    expect(loop.frames).toBeGreaterThan(1);
    expect(loop.ms).toBeGreaterThan(0);
    expect(loop.x).toBeGreaterThanOrEqual(0);
    expect(loop.x + loop.w).toBeLessThanOrEqual(loop.width * 1.25);
    expect(loop.y + loop.h).toBeLessThanOrEqual(loop.height);
  });
  it("keep room on the right only for a loop past the right edge", () => {
    expect(formReach("嘉然然龙")).toBeGreaterThan(0);
    expect(formReach("嘉然然龙")).toBeLessThanOrEqual(PET_BASE.width * 0.25);
    expect([formReach("乃琳法师"), formReach("贝拉炎头队长"), formReach("嘉然")]).toEqual([0, 0, 0]);
  });
});
