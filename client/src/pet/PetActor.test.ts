import { createSSRApp, defineComponent, getCurrentInstance, h } from "vue";
import { renderToString } from "vue/server-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Pos } from "../stores/desk";
import PetActor from "./PetActor.vue";

type Actor = {
  down(e: object): void; move(e: object): void; up(e: object): void; live: Pos | null;
};

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

/** Renders an actor and hands back its handlers, called here with the events the page would send. */
async function actor(extra: Record<string, unknown> = {}) {
  const seen = { moved: [] as Pos[], dragging: 0, tap: 0, drag: [] as boolean[] };
  let state: Actor | undefined;
  const Probe = defineComponent({
    setup() {
      // The dev build keeps a component's setup bindings on its instance.
      state = (getCurrentInstance()!.parent as unknown as { setupState: Actor }).setupState;
      return () => null;
    },
  });
  const props = {
    pos: { x: 100, y: 200 },
    place: (p: Pos) => ({ x: Math.max(0, p.x), y: p.y }),
    onMoved: (p: Pos) => seen.moved.push(p),
    onDragging: () => (seen.dragging += 1),
    onTap: () => (seen.tap += 1),
    onDrag: (on: boolean) => seen.drag.push(on),
    ...extra,
  };
  const html = await renderToString(createSSRApp({ render: () => h(PetActor, props, { default: () => h(Probe) }) }));
  const target = { closest: () => null };
  const ev = (type: string, e: Record<string, unknown> = {}) => ({ type, target, button: 0, pointerId: 1, clientX: 0, clientY: 0, ...e });
  const a = state!;
  return {
    html, seen, a,
    down: (e?: Record<string, unknown>) => a.down(ev("pointerdown", e)),
    move: (e?: Record<string, unknown>) => a.move(ev("pointermove", e)),
    up: (type = "pointerup", e?: Record<string, unknown>) => a.up(ev(type, e)),
  };
}

describe("a pet on the desk", () => {
  it("takes the mouse and stands at its place", async () => {
    const { html } = await actor();
    expect(html).toMatch(/^<div class="actor"[^>]* data-hit/);
    expect(html).toContain("transform:translate(100px, 200px)");
  });

  it("is a tap when the press ends where it started", async () => {
    const { seen, a, down, move, up } = await actor();
    down({ clientX: 10, clientY: 10 });
    move({ clientX: 12, clientY: 11 });
    up("pointerup");
    expect(a.live).toBeNull();
    expect(seen).toMatchObject({ moved: [], dragging: 0, tap: 1 });
  });

  it("follows the pointer by its place rule once it moved far enough, and reports where it was let go", async () => {
    const { seen, a, down, move, up } = await actor();
    down({ clientX: 10, clientY: 10 });
    move({ clientX: 30, clientY: 40 });
    expect(a.live).toEqual({ x: 120, y: 230 });
    move({ clientX: -500, clientY: 40 });
    expect(a.live).toEqual({ x: 0, y: 230 });
    // Another pointer moves nothing.
    move({ pointerId: 2, clientX: 900, clientY: 900 });
    expect(a.live).toEqual({ x: 0, y: 230 });
    up("pointerup");
    expect(seen.moved).toEqual([{ x: 0, y: 230 }]);
    expect(seen.dragging).toBe(2);
    expect(seen.tap).toBe(0);
    expect(a.live).toBeNull();
  });

  it("ends a drag the same way when the press is cancelled or the capture is lost, without a tap", async () => {
    for (const end of ["pointercancel", "lostpointercapture"]) {
      const { seen, a, down, move, up } = await actor();
      down({ clientX: 0, clientY: 0 });
      move({ clientX: 40, clientY: 0 });
      up(end);
      expect(seen.moved).toEqual([{ x: 140, y: 200 }]);
      expect(seen.tap).toBe(0);
      expect(a.live).toBeNull();
    }
  });

  it("ignores other buttons and presses on keys", async () => {
    const { seen, a, down, move, up } = await actor();
    down({ button: 2 });
    move({ clientX: 50, clientY: 50 });
    up("pointerup");
    down({ target: { closest: (s: string) => (s.includes("button") ? {} : null) } });
    move({ clientX: 50, clientY: 50 });
    up("pointerup");
    expect(a.live).toBeNull();
    expect(seen).toMatchObject({ moved: [], dragging: 0, tap: 0 });
  });
});

describe("a drag's start and end", () => {
  it("are told once each, the start when the press becomes a drag, and not for a tap", async () => {
    const { seen, down, move, up } = await actor();
    down({ clientX: 0, clientY: 0 });
    move({ clientX: 1, clientY: 0 });
    expect(seen.drag).toEqual([]);
    move({ clientX: 10, clientY: 0 });
    move({ clientX: 20, clientY: 0 });
    expect(seen.drag).toEqual([true]);
    up("pointerup");
    expect(seen.drag).toEqual([true, false]);
    // The end comes after the place it was let go at.
    expect(seen.moved).toHaveLength(1);
    down({ clientX: 0, clientY: 0 });
    up("pointerup");
    expect(seen.drag).toEqual([true, false]);
    expect(seen.tap).toBe(1);
  });
  it("is told when the drag is cancelled or the capture lost, once", async () => {
    const { seen, down, move, up } = await actor();
    down({ clientX: 0, clientY: 0 });
    move({ clientX: 30, clientY: 0 });
    up("pointercancel");
    up("lostpointercapture");
    expect(seen.drag).toEqual([true, false]);
  });
});

describe("a drag whose release never came", () => {
  it("is ended by the next press, so starts and ends stay paired", async () => {
    const { seen, down, move, up } = await actor();
    down({ clientX: 0, clientY: 0 });
    move({ clientX: 30, clientY: 0 });
    down({ clientX: 0, clientY: 0 });
    expect(seen.drag).toEqual([true, false]);
    move({ clientX: 30, clientY: 0 });
    up("pointerup");
    expect(seen.drag).toEqual([true, false, true, false]);
  });
});
