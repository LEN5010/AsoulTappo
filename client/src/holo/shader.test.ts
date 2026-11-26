import { describe, expect, it } from "vitest";
import { FLAT, frameKey, lightOf, MAX_TILT, sameFrame, tiltToward } from "./shader";

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

describe("holo frames", () => {
  const shine = { laserIntensity: 0.8, skinProtection: 0.5, clothBoost: 0.3, hueStart: 0.1, hueRange: 0.6 };
  it("are the same while nothing the shading takes has changed", () => {
    const a = frameKey(300, 450, { rx: 3, ry: -2 }, 1, shine);
    expect(sameFrame(null, a)).toBe(false);
    expect(sameFrame(a, frameKey(300, 450, { rx: 3, ry: -2 }, 1, { ...shine }))).toBe(true);
    // Past the edge the light stays where it is: the same picture.
    expect(sameFrame(frameKey(300, 450, { rx: 0, ry: 40 }, 1, shine), frameKey(300, 450, { rx: 0, ry: 50 }, 1, shine))).toBe(true);
  });
  it("differ with the lean, the light, the canvas size or the shine", () => {
    const a = frameKey(300, 450, { rx: 3, ry: -2 }, 1, shine);
    for (const b of [
      frameKey(300, 450, { rx: 3.01, ry: -2 }, 1, shine),
      frameKey(300, 450, { rx: 3, ry: -2 }, 0.85, shine),
      frameKey(301, 450, { rx: 3, ry: -2 }, 1, shine),
      frameKey(300, 451, { rx: 3, ry: -2 }, 1, shine),
      frameKey(300, 450, { rx: 3, ry: -2 }, 1, { ...shine, hueRange: 0.61 }),
      frameKey(300, 450, { rx: 3, ry: -2 }, 1, { ...shine, laserIntensity: 0.7 }),
    ]) expect(sameFrame(a, b)).toBe(false);
  });
});
