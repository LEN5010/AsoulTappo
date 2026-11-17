import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";
import { describe, expect, it } from "vitest";
import { characters } from "../characters";
import { characterColor } from "../manifest";
import PetView from "./PetView.vue";

describe("member click colors", () => {
  it.each(Object.keys(characters))("uses %s's support color on both buttons", async (character) => {
    const html = await renderToString(createSSRApp(PetView, {
      character, leftDown: true, rightDown: true, mouseDx: 7, mouseDy: -3,
    }));
    expect(html.match(/background-color:[^;" ]+/g)).toEqual([
      `background-color:${characterColor(character)}`,
      `background-color:${characterColor(character)}`,
    ]);
    expect(html).toContain(characters[character].leftClick);
    expect(html).toContain(characters[character].rightClick);
    expect(html.match(/mask-image:/g)).toHaveLength(4);
    expect(html.match(/translate\(7px,\s*-3px\)/g)).toHaveLength(3);
  });

  it.each([[false, false, 0], [true, false, 1], [false, true, 1]] as const)(
    "shows the pressed buttons: left=%s, right=%s",
    async (leftDown, rightDown, count) => {
      const html = await renderToString(createSSRApp(PetView, { character: "贝拉2025生日", leftDown, rightDown }));
      expect(html.match(/class="layer mouse click"/g) ?? []).toHaveLength(count);
    },
  );
});

describe("two-form skins", () => {
  it("lay the second picture, hidden, over the first", async () => {
    const html = await renderToString(createSSRApp(PetView, { character: "嘉然然龙" }));
    expect(html).toContain(characters["嘉然然龙"].form!.bgSmall);
    expect(html.match(/class="layer bg form"/g)).toHaveLength(1);
    expect(html).not.toContain("shown");
  });
  it("draw one picture for a skin without a second form", async () => {
    const html = await renderToString(createSSRApp(PetView, { character: "嘉然山海经" }));
    expect(html.match(/class="layer bg/g)).toHaveLength(1);
  });
});
