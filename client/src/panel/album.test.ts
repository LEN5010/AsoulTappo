import { describe, expect, it } from "vitest";
import { clampPan, clampScale, FIT, fitSize, MAX_SCALE, stepIndex, zoomAt } from "./album";

describe("stepIndex", () => {
  const list = ["a", "b", "c", "d", "e"].map((id) => ({ id }));
  const idOf = (c: { id: string }) => c.id;
  const ownedOf = (ids: string) => (c: { id: string }) => ids.includes(c.id);

  it("steps to the neighbours when everything is owned", () => {
    expect(stepIndex(list, "c", idOf, -1, () => true)).toBe(1);
    expect(stepIndex(list, "c", idOf, 1, () => true)).toBe(3);
  });

  it("stops at both ends", () => {
    expect(stepIndex(list, "a", idOf, -1, () => true)).toBe(-1);
    expect(stepIndex(list, "e", idOf, 1, () => true)).toBe(-1);
  });

  it("skips unowned items", () => {
    expect(stepIndex(list, "a", idOf, 1, ownedOf("ad"))).toBe(3);
    expect(stepIndex(list, "e", idOf, -1, ownedOf("ad"))).toBe(3);
  });

  it("scans from an unowned current item", () => {
    expect(stepIndex(list, "c", idOf, -1, ownedOf("ae"))).toBe(0);
    expect(stepIndex(list, "c", idOf, 1, ownedOf("ae"))).toBe(4);
  });

  it("finds nothing without owned neighbours or outside the list", () => {
    expect(stepIndex(list, "c", idOf, -1, ownedOf("c"))).toBe(-1);
    expect(stepIndex(list, "c", idOf, 1, ownedOf("c"))).toBe(-1);
    expect(stepIndex(list, "z", idOf, 1, () => true)).toBe(-1);
    expect(stepIndex([], "a", idOf, 1, () => true)).toBe(-1);
  });
});

describe("viewer zoom", () => {
  const box = { w: 800, h: 600 };
  const size = fitSize(2 / 3, box);

  it("fits the art by its limiting side", () => {
    expect(size).toEqual({ w: 400, h: 600 });
    expect(fitSize(16 / 9, box)).toEqual({ w: 800, h: 450 });
    expect(fitSize(1, { w: 0, h: 600 })).toEqual({ w: 0, h: 0 });
  });

  it("clamps the scale between fit and the maximum", () => {
    expect(clampScale(0.4)).toBe(1);
    expect(clampScale(2)).toBe(2);
    expect(clampScale(9)).toBe(MAX_SCALE);
  });

  it("keeps the point under the cursor in place", () => {
    const at = { x: 200, y: 300 };
    const view = zoomAt(FIT, 3, at, size, box);
    expect(view.scale).toBe(3);
    // The art point under the cursor maps back to the same spot.
    const local = { x: (at.x - view.x) / view.scale, y: (at.y - view.y) / view.scale };
    expect(local).toEqual(at);
  });

  it("centres an axis narrower than the box and closes gaps on a wider one", () => {
    // 2x: the art is 800 wide (the box exactly) and 1200 tall.
    const view = clampPan({ scale: 2, x: 500, y: 500 }, size, box);
    expect(view.x).toBe(-200);
    expect(view.y).toBe(0);
    const low = clampPan({ scale: 2, x: -999, y: -999 }, size, box);
    expect(low.y).toBe(-600);
    // 1.5x: 600 wide, narrower than the box, so it stays centred whatever the offset.
    expect(clampPan({ scale: 1.5, x: 300, y: 0 }, size, box).x).toBe(-100);
  });

  it("returns to fit when zoomed all the way out", () => {
    const zoomed = zoomAt(FIT, 3, { x: 10, y: 20 }, size, box);
    expect(zoomAt(zoomed, 0.5, { x: 300, y: 300 }, size, box)).toEqual(FIT);
  });
});
