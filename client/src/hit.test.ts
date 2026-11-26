import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { collectRects, sameRects, startHitReporter, type HitRect } from "./hit";

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

it("compares rectangle lists by value", () => {
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1 }], [{ x: 1, y: 1, w: 1, h: 1 }])).toBe(true);
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1 }], [])).toBe(false);
  // a rectangle that starts or stops taking the mouse under click-through is a change
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1, keep: true }], [{ x: 1, y: 1, w: 1, h: 1 }])).toBe(false);
  expect(sameRects([{ x: 1, y: 1, w: 1, h: 1, keep: true }], [{ x: 1, y: 1, w: 1, h: 1, keep: true }])).toBe(true);
});
