import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";
import { describe, expect, it } from "vitest";
import { characters, formReach } from "../characters";
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
  it("run no loop while the first picture shows", async () => {
    const html = await renderToString(createSSRApp(PetView, { character: "贝拉炎头队长" }));
    expect(html).toContain(characters["贝拉炎头队长"].form!.bgSmall);
    expect(html).not.toContain(characters["贝拉炎头队长"].form!.loop!.src);
  });
  it("draw one picture for a skin without a second form", async () => {
    const html = await renderToString(createSSRApp(PetView, { character: "嘉然山海经" }));
    expect(html.match(/class="layer bg/g)).toHaveLength(1);
  });
});

describe("see-through pets", () => {
  it("fade the figure only, never the bubbles beside it, and leave a solid pet as it was", async () => {
    const faded = await renderToString(createSSRApp(PetView, { character: "嘉然山海经", opacity: 0.4, sip: 1 }));
    expect(faded).toContain('<div class="art" style="opacity:0.4;"');
    expect(faded.match(/opacity:0\.4/g)).toHaveLength(1);
    const solid = await renderToString(createSSRApp(PetView, { character: "嘉然山海经", opacity: 1 }));
    expect(solid).toMatch(/<div class="art"( style="")? data-v/);
  });
});

describe("the second form's wing past the picture", () => {
  const reachOf = (html: string) => html.match(/<span class="reach"[^>]*>/g) ?? [];
  it("takes the mouse on the desk while the second form shows", async () => {
    const html = await renderToString(createSSRApp(PetView, { character: "嘉然然龙", form: true, reachHit: true, scale: 1 }));
    const [reach, ...more] = reachOf(html);
    expect(more).toHaveLength(0);
    expect(reach).toContain("data-hit");
    // Right of the 240px picture, as wide as the loop draws past it (formReach).
    expect(reach).toContain("left:240px;");
    const width = Number(/width:([\d.]+)px/.exec(reach!)![1]);
    expect(width).toBeCloseTo(formReach("嘉然然龙"), 5);
    expect(width).toBeGreaterThan(36);
    const twice = reachOf(await renderToString(createSSRApp(PetView, { character: "嘉然然龙", form: true, reachHit: true, scale: 2 })));
    expect(Number(/width:([\d.]+)px/.exec(twice[0]!)![1])).toBeCloseTo(formReach("嘉然然龙") * 2, 5);
  });
  it("leaves the sides empty in the first form, for skins whose loop stays on the picture and off the desk", async () => {
    for (const props of [
      { character: "嘉然然龙", form: false, reachHit: true },
      { character: "嘉然然龙", form: true },
      { character: "乃琳法师", form: true, reachHit: true },
      { character: "嘉然山海经", reachHit: true },
    ]) {
      expect(reachOf(await renderToString(createSSRApp(PetView, props)))).toHaveLength(0);
    }
  });
});

describe("the own pet's paws", () => {
  const kb = (html: string) => /<img class="(down )?layer kb"[^>]*style="([^"]*)"/.exec(html);
  it("press the keyboard paw down by the press offset at the pet's size, and put it back up", async () => {
    const down = kb(await renderToString(createSSRApp(PetView, { character: "嘉然山海经", keyDown: true, scale: 2 })))!;
    expect(down[1]).toBe("down ");
    expect(down[2]).toContain("transform:translateY(10px)");
    const up = kb(await renderToString(createSSRApp(PetView, { character: "嘉然山海经", scale: 2 })))!;
    expect(up[1]).toBeUndefined();
    expect(up[2]).toContain("transform:translateY(0px)");
  });
  it("move the mouse paw and its pressed buttons together, at the pet's size", async () => {
    const html = await renderToString(createSSRApp(PetView, {
      character: "嘉然山海经", scale: 1.5, mouseDx: 4, mouseDy: -2, leftDown: true,
    }));
    expect(html.match(/class="layer mouse[^"]*"[^>]*style="[^"]*transform:translate\(6px, -3px\)/g)).toHaveLength(2);
  });
});

describe("the own pet given its pose", () => {
  it("keeps both button layers, hidden, and moves no layer by a render", async () => {
    const pose = { keyDown: true, left: true, right: false, dx: 7, dy: -3, formPress: 2 };
    const html = await renderToString(createSSRApp(PetView, { character: "乃琳", pose, opacity: 0.5 }));
    expect(html).toContain("direct-pose");
    expect(html).not.toContain("remote-motion");
    expect(html).toContain("click-left");
    expect(html).toContain("click-right");
    expect(html).not.toContain("translate(");
    expect(html).not.toContain("translateY(");
    expect(html).not.toMatch(/class="[^"]*\bdown\b/);
    // The figure fades as before.
    expect(html).toContain('<div class="art" style="opacity:0.5;"');
  });
});
