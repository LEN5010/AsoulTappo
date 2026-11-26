import { describe, expect, it } from "vitest";
import { watch } from "vue";
import {
  DOCK_SNAP, FORMATION_GAP, defaultFormation, dockY, formationCells, formationOffset, formationSize, inLastRow,
  panX, placeFormation, resetOwnPet, tidyRemotes,
} from "./desk";
import { settings } from "./settings";

const vp = { w: 1920, h: 1080 };
const size = { w: 100, h: 80 };
const pitch = { x: size.w + FORMATION_GAP, y: size.h + FORMATION_GAP };

describe("formation cells", () => {
  it("fills rows of `cols` left to right, top to bottom", () => {
    expect(formationCells({ x: 10, y: 20 }, 5, 2, size)).toEqual([
      { x: 10, y: 20 }, { x: 10 + pitch.x, y: 20 },
      { x: 10, y: 20 + pitch.y }, { x: 10 + pitch.x, y: 20 + pitch.y },
      { x: 10, y: 20 + 2 * pitch.y },
    ]);
    expect(formationOffset(7, 3, size)).toEqual({ x: pitch.x, y: 2 * pitch.y });
  });
  it("is only as wide as its pets when there are fewer than `cols`", () => {
    expect(formationSize(3, 5, size)).toEqual({ w: 3 * size.w + 2 * FORMATION_GAP, h: size.h });
    expect(formationSize(20, 5, size)).toEqual({ w: 5 * size.w + 4 * FORMATION_GAP, h: 4 * size.h + 3 * FORMATION_GAP });
    expect(formationSize(0, 5, size)).toEqual({ w: 0, h: 0 });
    expect(formationCells({ x: 0, y: 0 }, 0, 5, size)).toEqual([]);
  });
  it("tells the last row, also when it is not full", () => {
    expect([0, 1, 2, 3, 4].map((i) => inLastRow(i, 5, 2))).toEqual([false, false, false, false, true]);
    expect([0, 1, 2].map((i) => inLastRow(i, 3, 5))).toEqual([true, true, true]);
  });
});

describe("placeFormation", () => {
  it("keeps a floating formation fully on screen", () => {
    const full = formationSize(6, 3, size);
    expect(placeFormation({ x: -50, y: -50 }, 6, 3, size, 1, vp)).toEqual({ anchor: { x: 8, y: 8 }, docked: false });
    expect(placeFormation({ x: 5000, y: 300 }, 6, 3, size, 1, vp).anchor).toEqual({ x: vp.w - full.w - 8, y: 300 });
  });
  it("docks once the last row comes within the snap distance of the bottom edge", () => {
    const lastRow = formationSize(6, 3, size).h - size.h;
    const bottom = dockY(1, vp);
    const near = placeFormation({ x: 400, y: bottom - DOCK_SNAP - lastRow }, 6, 3, size, 1, vp);
    expect(near).toEqual({ anchor: { x: 400, y: bottom - lastRow }, docked: true });
    expect(formationCells(near.anchor, 6, 3, size)[5].y).toBe(bottom);
    const far = placeFormation({ x: 400, y: bottom - DOCK_SNAP - lastRow - 1 }, 6, 3, size, 1, vp);
    expect(far.docked).toBe(false);
  });
  it("keeps a docked formation's last row on the edge as rows come and go", () => {
    const bottom = dockY(0.5, vp);
    for (const n of [2, 3, 7]) {
      const placed = placeFormation({ x: 400, y: 100 }, n, 2, size, 0.5, vp, true);
      expect(placed.docked).toBe(true);
      expect(formationCells(placed.anchor, n, 2, size).at(-1)!.y).toBe(bottom);
    }
  });
  it("keeps a docked formation's x on screen", () => {
    const full = formationSize(4, 4, size);
    expect(placeFormation({ x: 5000, y: 0 }, 4, 4, size, 1, vp, true).anchor.x).toBe(vp.w - full.w - 8);
  });
});

describe("defaultFormation", () => {
  const ownSize = { w: 240, h: 170 };
  it("stands to the left of the own pet, bottom-aligned with it", () => {
    const own = { x: 1500, y: 800 };
    const full = formationSize(4, 5, size);
    expect(defaultFormation(own, ownSize, false, 4, 5, size, 1, vp)).toEqual({
      anchor: { x: own.x - FORMATION_GAP - full.w, y: own.y + ownSize.h - full.h }, docked: false,
    });
  });
  it("goes to the right when the left has no room, and is clamped when neither has", () => {
    const right = defaultFormation({ x: 100, y: 800 }, ownSize, false, 4, 5, size, 1, vp);
    expect(right.anchor.x).toBe(100 + ownSize.w + FORMATION_GAP);
    const narrow = { w: 600, h: 1080 };
    expect(defaultFormation({ x: 100, y: 800 }, ownSize, false, 4, 5, size, 1, narrow).anchor.x).toBe(8);
  });
  it("docks next to a docked own pet", () => {
    const placed = defaultFormation({ x: 1500, y: dockY(1, vp) }, ownSize, true, 7, 5, size, 1, vp);
    expect(placed.docked).toBe(true);
    expect(formationCells(placed.anchor, 7, 5, size)[6].y).toBe(dockY(1, vp));
  });
});

describe("partners in a row on the bottom edge", () => {
  it("all stand in one row, which may run off the screen's sides", () => {
    const narrow = { w: 500, h: 1080 };
    const full = formationSize(9, 9, size);
    expect(full.w).toBeGreaterThan(narrow.w);
    const placed = defaultFormation({ x: 300, y: 500 }, { w: 240, h: 170 }, true, 9, 9, size, 0.5, narrow, true);
    expect(placed).toEqual({ anchor: { x: narrow.w - 8 - full.w, y: dockY(0.5, narrow) }, docked: true });
    const cells = formationCells(placed.anchor, 9, 9, size);
    expect(new Set(cells.map((c) => c.y))).toEqual(new Set([dockY(0.5, narrow)]));
    expect(cells.at(-1)!.x + size.w).toBe(narrow.w - 8);
  });
  it("move sideways until either end is on screen when the row is wider than it", () => {
    const narrow = { w: 500, h: 1080 };
    const full = formationSize(9, 9, size);
    const at = (x: number) => placeFormation({ x, y: 0 }, 9, 9, size, 1, narrow, true, true).anchor.x;
    expect(at(5000)).toBe(8);
    expect(at(-5000)).toBe(narrow.w - 8 - full.w);
    expect(at(-200)).toBe(-200);
    // While it fits, the row stays on screen as before.
    expect(placeFormation({ x: -50, y: 0 }, 2, 2, size, 1, vp, true, true).anchor.x).toBe(8);
    expect(placeFormation({ x: 5000, y: 0 }, 2, 2, size, 1, vp, true, true).anchor.x).toBe(vp.w - 8 - formationSize(2, 2, size).w);
    expect(panX(40, 300, vp)).toBe(40);
  });
  it("stand next to the own pet on the edge, also when it floats higher up", () => {
    const own = { x: 1500, y: 300 };
    const placed = defaultFormation(own, { w: 240, h: 170 }, true, 4, 4, size, 1, vp, true);
    expect(placed).toEqual({ anchor: { x: own.x - FORMATION_GAP - formationSize(4, 4, size).w, y: dockY(1, vp) }, docked: true });
  });
  it("only move sideways when dragged", () => {
    const placed = placeFormation({ x: 300, y: 100 }, 4, 4, size, 1, vp, true);
    expect(placed).toEqual({ anchor: { x: 300, y: dockY(1, vp) }, docked: true });
  });
  it("go back next to the own pet on tidying, keeping the formation's place", () => {
    const before = { partnerLayout: settings.partnerLayout, partnerRowX: settings.partnerRowX, formationX: settings.formationX };
    try {
      Object.assign(settings, { partnerLayout: "row", partnerRowX: 300, formationX: 40 });
      tidyRemotes();
      expect(settings.partnerRowX).toBe(-1);
      expect(settings.formationX).toBe(40);
    } finally {
      Object.assign(settings, before);
    }
  });
});

describe("resetOwnPet", () => {
  it("takes a docked own pet off the bottom edge before it gives up its place", () => {
    const before = { petDocked: settings.petDocked, petX: settings.petX, petY: settings.petY };
    Object.assign(settings, { petDocked: true, petX: 300, petY: 900 });
    // In the panel each change reaches the desk as its own patch, in this order.
    const order: string[] = [];
    const stops = (["petDocked", "petX", "petY"] as const).map((key) =>
      watch(() => settings[key], () => order.push(key), { flush: "sync" }));
    try {
      resetOwnPet();
      expect(order).toEqual(["petDocked", "petX", "petY"]);
      expect({ petDocked: settings.petDocked, petX: settings.petX, petY: settings.petY })
        .toEqual({ petDocked: false, petX: -1, petY: -1 });
    } finally {
      for (const stop of stops) stop();
      Object.assign(settings, before);
    }
  });
});
