import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";
import { describe, expect, it } from "vitest";
import PetView from "./PetView.vue";
import { pawPainter, type PawPose } from "./pawPaint";
import { FakeNode } from "./testNodes";

/** A pet's layers as PetView draws them for a pose of its own: the paws, and the two buttons over the mouse paw. */
function layers() {
  const root = new FakeNode("div");
  const art = root.append(new FakeNode("div"));
  const make = (className: string) => Object.assign(art.append(new FakeNode("span")), { className });
  return {
    root,
    kb: make("layer kb"),
    mouse: make("layer mouse"),
    left: make("layer mouse click click-left"),
    right: make("layer mouse click click-right"),
  };
}

/** What the template draws for [pose] when given it as props: the keyboard paw, the mouse layers, the shown buttons. */
async function drawnByProps(pose: PawPose, scale: number) {
  const html = await renderToString(createSSRApp(PetView, {
    character: "嘉然山海经", scale, keyDown: pose.keyDown, mouseDx: pose.dx, mouseDy: pose.dy, leftDown: pose.left, rightDown: pose.right,
  }));
  const kb = /<img class="(down )?layer kb"[^>]*style="[^"]*transform:([^;"]+)/.exec(html)!;
  const mouse = [...html.matchAll(/class="layer mouse[^"]*"[^>]*style="[^"]*transform:([^;"]+)/g)].map((m) => m[1]);
  const clicks = html.match(/class="layer mouse click"/g)?.length ?? 0;
  return { down: !!kb[1], kb: kb[2], mouse: mouse[0], layers: mouse.length, clicks };
}

describe("painting a pet's paws straight onto its layers", () => {
  const poses: [PawPose, number][] = [
    [{ dx: 0, dy: 0, keyDown: false, left: false, right: false }, 1],
    [{ dx: 7, dy: -3, keyDown: true, left: true, right: false }, 1],
    [{ dx: -12.5, dy: 4.25, keyDown: false, left: false, right: true }, 1.5],
    [{ dx: 20, dy: 20, keyDown: true, left: true, right: true }, 2.4],
  ];
  it.each(poses)("draws what the template draws for %o at %d", async (pose, scale) => {
    const want = await drawnByProps(pose, scale);
    const l = layers();
    pawPainter(l.root as unknown as HTMLElement, scale)(pose, pose.keyDown);
    expect(l.kb.style.transform).toBe(want.kb);
    expect(l.kb.classList.contains("down")).toBe(want.down);
    for (const layer of [l.mouse, l.left, l.right]) expect(layer.style.transform).toBe(want.mouse);
    const shown = [l.left, l.right].filter((c) => c.style.display === "block").length;
    expect(shown).toBe(want.clicks);
    expect([l.left, l.right].every((c) => c.style.display === "block" || c.style.display === "none")).toBe(true);
  });

  it("presses the keyboard paw for a pressed beat while no key is held, and lets it up after", () => {
    const l = layers();
    const paint = pawPainter(l.root as unknown as HTMLElement, 2);
    const pose = { dx: 0, dy: 0, keyDown: false, left: false, right: false };
    paint(pose, true);
    expect(l.kb.style.transform).toBe("translateY(10px)");
    expect(l.kb.classList.contains("down")).toBe(true);
    paint(pose, false);
    expect(l.kb.style.transform).toBe("translateY(0px)");
    expect(l.kb.classList.contains("down")).toBe(false);
  });
});
