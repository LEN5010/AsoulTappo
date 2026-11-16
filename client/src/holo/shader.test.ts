import { describe, expect, it } from "vitest";
import { FLAT, lightOf, MAX_TILT, tiltToward } from "./shader";

describe("holo lean", () => {
  it("leans at most MAX_TILT either way toward the pointer", () => {
    expect(tiltToward(0.5, 0.5)).toEqual({ rx: 0, ry: 0 });
    expect(tiltToward(1, 0)).toEqual({ rx: MAX_TILT, ry: MAX_TILT });
    expect(tiltToward(-3, 9)).toEqual({ rx: -MAX_TILT, ry: -MAX_TILT });
  });

  it("puts the light where the demo does: under the pointer, centred when level", () => {
    expect(lightOf(FLAT)).toEqual({ x: 0.5, y: 0.5 });
    const right = lightOf(tiltToward(1, 0.5));
    expect(right.x).toBeGreaterThan(0.9);
    expect(right.y).toBe(0.5);
    expect(lightOf({ rx: 40, ry: -40 })).toEqual({ x: 0, y: 0 });
  });
});
