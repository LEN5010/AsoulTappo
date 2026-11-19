import { describe, expect, it } from "vitest";
import { edgeShift } from "./lift";

describe("a plate hung from the strip next to a screen edge", () => {
  const vw = 1000;
  it("stays where it is while it fits", () => {
    expect(edgeShift(4, 300, vw)).toBe(0);
    expect(edgeShift(696, 300, vw)).toBe(0);
  });
  it("moves right off the left edge and left off the right edge, to 4px inside", () => {
    expect(edgeShift(-60, 280, vw)).toBe(64);
    expect(edgeShift(800, 280, vw)).toBe(-84);
  });
  it("keeps its left edge on screen when it is wider than the screen", () => {
    expect(edgeShift(100, 1200, vw)).toBe(-96);
    expect(edgeShift(-10, 1200, vw)).toBe(14);
  });
});
