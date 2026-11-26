import { describe, expect, it } from "vitest";
import { PLATE_GRIP, STRIP_WIDTH, emotePlace, ownDeskWidth, ownXRange, remotePetSize, stripFit } from "./bounds";
import { PET_BASE, headAnchor } from "../characters";

describe("the strip under the own pet", () => {
  it("shrinks as a whole to the width of a pet narrower than it", () => {
    for (const scale of [0.5, 0.6, 0.8]) {
      const fit = stripFit(scale);
      expect(fit.layout).toBe(STRIP_WIDTH);
      expect(fit.width).toBeCloseTo(PET_BASE.width * scale);
      expect(fit.zoom).toBeCloseTo((PET_BASE.width * scale) / STRIP_WIDTH);
      expect(fit.zoom).toBeLessThan(1);
    }
  });

  it("is as wide as the pet and drawn at full size from the pet's width up, as before", () => {
    const before = (scale: number) => Math.max(STRIP_WIDTH, PET_BASE.width * scale);
    for (const scale of [STRIP_WIDTH / PET_BASE.width, 0.9, 1, 1.5, 2, 3]) {
      expect(stripFit(scale)).toEqual({ layout: before(scale), zoom: 1, width: before(scale) });
    }
  });

  it("keeps the size set for it whatever the pet's, as wide as a wider pet", () => {
    for (const own of [0.6, 1, 1.5]) {
      for (const scale of [0.5, 0.8, 1, 2]) {
        const fit = stripFit(scale, own);
        expect(fit.zoom).toBe(own);
        expect(fit.width).toBeCloseTo(Math.max(STRIP_WIDTH * own, PET_BASE.width * scale));
        expect(fit.layout * fit.zoom).toBeCloseTo(fit.width);
        expect(fit.layout).toBeGreaterThanOrEqual(STRIP_WIDTH);
      }
    }
    // At full size it is the strip of 1.2.5.
    for (const scale of [0.5, 0.8, 1, 2]) {
      expect(stripFit(scale, 1).width).toBe(Math.max(STRIP_WIDTH, PET_BASE.width * scale));
    }
  });

  it("leaves the own pet's width to the plate handles, so a small pet reaches as close to the edge as a large one", () => {
    const before = (scale: number) =>
      Math.max(Math.max(STRIP_WIDTH, PET_BASE.width * scale), Math.round(PET_BASE.width * scale) + PLATE_GRIP * 2);
    for (const scale of [0.9, 1, 1.3, 2, 3]) expect(ownDeskWidth(scale)).toBe(before(scale));
    expect(ownDeskWidth(0.5)).toBe(120 + PLATE_GRIP * 2);
    expect(before(0.5)).toBe(STRIP_WIDTH);
    for (const scale of [0.5, 0.6, 0.7, 0.8]) {
      expect(ownDeskWidth(scale) - PET_BASE.width * scale).toBeCloseTo(PLATE_GRIP * 2, 0);
    }
  });
});

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

describe("the emote over a pet", () => {
  const vp = { w: 1920, h: 1080 };
  const at = (x: number, y: number, scale = 1, character = "贝拉", min = 56) => emotePlace({ x, y }, character, scale, min, vp);
  /** Top of the picture and its badge on screen, as PetView draws them. */
  const top = (y: number, scale: number, character: string, min: number) =>
    y + (headAnchor(character).y + 16) * scale + at(400, y, scale, character, min).bubbleShift.y - Math.max(min, 72 * scale) - 20;

  it("stays over the head while there is room for it", () => {
    expect(at(400, 500)).toEqual({ flipBubble: false, bubbleShift: { x: 0, y: 0 } });
  });

  it("moves down beside the head at the top of the screen, on every pet and size", () => {
    for (const character of ["嘉然", "乃琳", "贝拉", "心宜", "思诺", "贝拉2025生日"]) {
      for (const scale of [0.4, 0.5, 1, 2, 3]) {
        for (const min of [44, 56]) {
          for (const y of [0, 8, 30]) expect(top(y, scale, character, min)).toBeGreaterThanOrEqual(3.5);
        }
      }
    }
    expect(at(400, 8).bubbleShift.x).toBeGreaterThan(0);
  });

  it("moves down less the more room there is over the pet", () => {
    const shifts = [8, 20, 40, 80].map((y) => at(400, y).bubbleShift.y);
    expect(shifts).toEqual([...shifts].sort((a, b) => b - a));
    expect(shifts.at(-1)).toBe(0);
  });

  it("goes to the other side of the head next to the right edge, also where it moves down", () => {
    expect(at(1900, 500)).toEqual({ flipBubble: true, bubbleShift: { x: 0, y: 0 } });
    const low = at(1900, 8);
    expect(low.flipBubble).toBe(true);
    expect(low.bubbleShift.x).toBeLessThan(0);
  });

  it("is moved no further for a pet above the screen's top than for one standing at it", () => {
    expect(at(400, -300)).toEqual(at(400, 0));
  });
});

describe("the own pet against the side edges", () => {
  it("lets the empty bands beside the picture stand out past the screen, so the picture reaches the edges", () => {
    for (const scale of [0.6, 1, 1.4]) {
      const width = ownDeskWidth(scale);
      const pet = PET_BASE.width * scale;
      const band = Math.floor((width - pet) / 2);
      const { min, max } = ownXRange(width, band, 0, 1707);
      // the picture's left edge on the screen's left edge, its right edge on the right one, at most half a pixel in
      expect(min + (width - pet) / 2).toBeGreaterThanOrEqual(0);
      expect(min + (width - pet) / 2).toBeLessThanOrEqual(0.5);
      expect(max + (width + pet) / 2).toBeLessThanOrEqual(1707);
      expect(max + (width + pet) / 2).toBeGreaterThanOrEqual(1706.5);
    }
  });

  it("keeps what a second form draws past the picture on screen", () => {
    const { max } = ownXRange(268, 14, 30, 1707);
    expect(max + 14 + 240 + 30).toBe(1707);
  });

  it("puts a box wider than the screen at its left edge", () => {
    expect(ownXRange(268, 14, 0, 200)).toEqual({ min: -14, max: -14 });
  });
});
