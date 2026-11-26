import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { collectRects, sameRects, startHitReporter, type HitRect } from "./hit";
import { FakeNode } from "./pet/testNodes";

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("requestAnimationFrame", (cb: () => void) => setTimeout(cb, 16) as unknown as number);
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("sends rectangles once at start and then only when they change", () => {
  let rects: HitRect[] = [{ x: 1, y: 2, w: 3, h: 4 }];
  const sent: HitRect[][] = [];
  const r = startHitReporter((x) => sent.push(x), () => rects.map((v) => ({ ...v })), 200);
  expect(sent).toHaveLength(1);
  vi.advanceTimersByTime(1000);
  expect(sent).toHaveLength(1);
  rects = [{ x: 5, y: 2, w: 3, h: 4 }];
  r.kick();
  r.kick();
  vi.advanceTimersByTime(16);
  expect(sent).toHaveLength(2);
  rects = [];
  vi.advanceTimersByTime(200);
  expect(sent.at(-1)).toEqual([]);
  r.stop();
  rects = [{ x: 0, y: 0, w: 1, h: 1 }];
  vi.advanceTimersByTime(1000);
  expect(sent).toHaveLength(3);
});

it("sends the page scale and resends when only the scale changes", () => {
  const rects: HitRect[] = [{ x: 1, y: 2, w: 3, h: 4 }];
  let scale = 1.5;
  const sent: [HitRect[], number][] = [];
  const r = startHitReporter((x, s) => sent.push([x, s]), () => rects.map((v) => ({ ...v })), 200, () => scale);
  expect(sent).toEqual([[rects, 1.5]]);
  vi.advanceTimersByTime(200);
  expect(sent).toHaveLength(1);
  scale = 1.875;
  vi.advanceTimersByTime(200);
  expect(sent.at(-1)).toEqual([rects, 1.875]);
  r.stop();
});

it("leaves out the sides an element draws nothing on", () => {
  const el = (left: number, top: number, width: number, height: number, dataset: Record<string, string>) => ({
    dataset,
    getBoundingClientRect: () => ({ left, top, width, height, right: left + width, bottom: top + height }),
  });
  const root = {
    querySelectorAll: () => [
      el(100.5, 50, 268, 170, { hit: "", hitInset: "14" }),
      el(10, 10, 20, 10, { hit: "keep", hitInset: "0" }),
      // nothing is left of one narrower than its two sides
      el(0, 0, 40, 40, { hit: "", hitInset: "20" }),
    ],
  } as unknown as ParentNode;
  expect(collectRects(root)).toEqual([{ x: 114, y: 50, w: 241, h: 170 }, { x: 10, y: 10, w: 20, h: 10, keep: true }]);
});

it("skips sampling while paused and samples once resumed", () => {
  let rects: HitRect[] = [{ x: 1, y: 2, w: 3, h: 4 }];
  let collects = 0;
  const sent: HitRect[][] = [];
  const r = startHitReporter((x) => sent.push(x), () => { collects += 1; return rects.map((v) => ({ ...v })); }, 200);
  r.kick();
  r.setPaused(true);
  rects = [{ x: 50, y: 60, w: 3, h: 4 }];
  r.kick();
  vi.advanceTimersByTime(600);
  expect(collects).toBe(1);
  expect(sent).toHaveLength(1);
  r.setPaused(false);
  vi.advanceTimersByTime(16);
  expect(collects).toBe(2);
  expect(sent.at(-1)).toEqual([{ x: 50, y: 60, w: 3, h: 4 }]);
  r.stop();
});

it("compares rectangle lists by value", () => {
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1 }], [{ x: 1, y: 1, w: 1, h: 1 }])).toBe(true);
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1 }], [])).toBe(false);
  // a rectangle that starts or stops taking the mouse under click-through is a change
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1, keep: true }], [{ x: 1, y: 1, w: 1, h: 1 }])).toBe(false);
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1, keep: true }], [{ x: 1, y: 1, w: 1, h: 1, keep: true }])).toBe(true);
});

describe("the reporter on a page", () => {
  type Opts = MutationObserverInit;
  let observers: FakeMutations[] = [];
  /** Delivers a change of [node] to every observer that would see it in a browser, as one record each. */
  class FakeMutations {
    targets = new Map<FakeNode, Opts>();
    calls = 0;
    constructor(public cb: (records: unknown[]) => void) { observers.push(this); }
    observe(target: FakeNode, options: Opts) { this.targets.set(target, options); }
    disconnect() { this.targets.clear(); }
    takeRecords() { return []; }
    sees(node: FakeNode, attr?: string) {
      for (const [target, o] of this.targets) {
        if (target !== node && !(o.subtree && contains(target, node))) continue;
        if (attr ? o.attributes && (!o.attributeFilter || o.attributeFilter.includes(attr)) : o.childList) return true;
      }
      return false;
    }
  }
  const contains = (a: FakeNode, b: FakeNode) => { for (let n: FakeNode | null = b; n; n = n.parentElement) if (n === a) return true; return false; };
  function attr(node: FakeNode, name: string) {
    for (const o of observers) if (o.sees(node, name)) { o.calls++; o.cb([{ type: "attributes", target: node, attributeName: name }]); }
  }
  function add(parent: FakeNode, child: FakeNode) {
    parent.append(child);
    for (const o of observers) if (o.sees(parent)) { o.calls++; o.cb([{ type: "childList", target: parent, addedNodes: [child], removedNodes: [] }]); }
  }

  let root: FakeNode, desk: FakeNode, actor: FakeNode, art: FakeNode, mouse: FakeNode;
  let collects = 0;
  beforeEach(() => {
    observers = [];
    collects = 0;
    root = new FakeNode("html");
    desk = root.append(new FakeNode("div"));
    actor = desk.append(new FakeNode("div"));
    actor.attrs["data-hit"] = "";
    art = actor.append(new FakeNode("div"));
    mouse = art.append(new FakeNode("img"));
    vi.stubGlobal("Element", FakeNode);
    vi.stubGlobal("MutationObserver", FakeMutations);
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    vi.stubGlobal("document", {
      documentElement: root, querySelectorAll: (s: string) => root.querySelectorAll(s),
      addEventListener() {}, removeEventListener() {},
    });
    vi.stubGlobal("window", { addEventListener() {}, removeEventListener() {} });
  });
  const start = () => startHitReporter(() => {}, () => { collects += 1; return [{ x: collects, y: 0, w: 1, h: 1 }]; });
  const settle = () => vi.advanceTimersByTime(16);

  it("measures again when a hit target or what holds it changes, not for the layers drawn inside it", () => {
    const r = start();
    expect(collects).toBe(1);
    attr(actor, "style");
    settle();
    expect(collects).toBe(2);
    attr(desk, "class");
    settle();
    expect(collects).toBe(3);
    attr(mouse, "style");
    attr(art, "class");
    settle();
    expect(collects).toBe(3);
    r.stop();
  });

  it("follows hit targets that come later, and leaves alone what comes without one", () => {
    const r = start();
    const bubble = new FakeNode("div");
    add(actor, bubble);
    settle();
    expect(collects).toBe(1);
    const key = new FakeNode("div");
    key.attrs["data-hit"] = "keep";
    const holder = new FakeNode("div");
    holder.append(key);
    add(desk, holder);
    settle();
    expect(collects).toBe(2);
    attr(key, "style");
    settle();
    expect(collects).toBe(3);
    bubble.attrs["data-hit"] = "";
    attr(bubble, "data-hit");
    settle();
    expect(collects).toBe(4);
    attr(bubble, "class");
    settle();
    expect(collects).toBe(5);
    r.stop();
  });

  it("samples nothing while paused, and measures again on resuming, hit targets that came meanwhile too", () => {
    const r = start();
    r.setPaused(true);
    attr(actor, "style");
    const key = new FakeNode("div");
    key.attrs["data-hit"] = "";
    add(desk, key);
    vi.advanceTimersByTime(500);
    expect(collects).toBe(1);
    r.setPaused(false);
    settle();
    expect(collects).toBe(2);
    attr(key, "style");
    settle();
    expect(collects).toBe(3);
    r.stop();
  });

  it("is not even told when a layer inside a hit target moves", () => {
    const r = start();
    for (let i = 0; i < 60; i++) attr(mouse, "style");
    expect(observers.reduce((n, o) => n + o.calls, 0)).toBe(0);
    r.stop();
  });
});
