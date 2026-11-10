import { describe, expect, it } from "vitest";
import { remotePetSize } from "./bounds";
import { PET_BASE } from "../characters";

it.each([[false, 16], [true, 17]])("keeps names within a small partner, plates=%s", (plates, band) => {
  const size = remotePetSize(0.4, true, plates);
  expect(size.w).toBeCloseTo(PET_BASE.width * 0.4);
  expect(size.h).toBeCloseTo(PET_BASE.height * 0.4 + band);
});
it("does not reserve a name band while names are hidden", () => {
  expect(remotePetSize(0.4, false, true)).toEqual({ w: PET_BASE.width * 0.4, h: PET_BASE.height * 0.4 });
});
it("preserves normal-size bounds", () => {
  expect(remotePetSize(1, true, false)).toEqual({ w: PET_BASE.width, h: PET_BASE.height + 22 });
});

import { DESK_GAP, DOCK_SNAP, dockY, placePet } from "../stores/desk";

describe("the own pet on the bottom edge", () => {
  const vp = { w: 1000, h: 700 };
  const full = { w: 240, h: 135 + 36 };

  it("stands with its desk on the edge: the empty picture under the desk is off screen", () => {
    expect(dockY(1, vp)).toBe(700 - 135 + DESK_GAP);
    expect(dockY(2, vp)).toBe(700 - (135 - DESK_GAP) * 2);
  });

  it("snaps into place once dragged close, and keeps the strip on screen above that", () => {
    const edge = dockY(1, vp);
    expect(placePet({ x: 300, y: edge - DOCK_SNAP }, full, 1, vp)).toEqual({ pos: { x: 300, y: edge }, docked: true });
    expect(placePet({ x: 300, y: 5000 }, full, 1, vp)).toEqual({ pos: { x: 300, y: edge }, docked: true });
    const above = placePet({ x: 300, y: edge - DOCK_SNAP - 1 }, full, 1, vp);
    expect(above).toEqual({ pos: { x: 300, y: 700 - full.h - 8 }, docked: false });
    expect(placePet({ x: 300, y: 200 }, full, 1, vp)).toEqual({ pos: { x: 300, y: 200 }, docked: false });
  });

  it("stays between the side edges while docked", () => {
    expect(placePet({ x: -50, y: 5000 }, full, 1, vp).pos.x).toBe(8);
    expect(placePet({ x: 5000, y: 5000 }, full, 1, vp).pos.x).toBe(1000 - 240 - 8);
  });
});

import { nextDockSlot } from "../stores/desk";

describe("partners next to a docked own pet", () => {
  const vp = { w: 1000, h: 700 };
  const own = { x: 600, y: 0 };
  const ownSize = { w: 240, h: 135 };
  const size = { w: 150, h: 110 };

  it("stand on the edge, first to the left of the own pet", () => {
    expect(nextDockSlot(own, ownSize, size, [], vp)).toEqual({ x: 600 - 166, y: 0, docked: true });
  });

  it("skip places taken by docked partners and ignore those standing higher up", () => {
    const left = { x: 434, y: 0, docked: true };
    expect(nextDockSlot(own, ownSize, size, [left], vp)).toEqual({ x: 600 - 2 * 166, y: 0, docked: true });
    expect(nextDockSlot(own, ownSize, size, [{ x: 434, y: 200 }], vp)?.x).toBe(434);
  });

  it("give up when the edge is full", () => {
    const narrow = { w: 420, h: 700 };
    expect(nextDockSlot({ x: 100, y: 0 }, ownSize, size, [], narrow)).toBeNull();
  });
});
