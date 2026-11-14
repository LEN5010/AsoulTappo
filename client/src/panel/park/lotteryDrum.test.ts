import { expect, it } from "vitest";
import { Drum, STEP } from "./lotteryDrum";

const DIGITS = "0123456789".split("");
function filled(seed = 7) {
  const drum = new Drum(68, 13.5, (38 * Math.PI) / 180, seed);
  for (const d of DIGITS) drum.add(d);
  return drum;
}
function inside(drum: Drum) {
  for (const b of drum.balls) expect(Math.hypot(b.x, b.y)).toBeLessThanOrEqual(drum.R - drum.r + 0.5);
}
function apart(drum: Drum, slack = 1.5) {
  const { balls, r } = drum;
  for (let i = 0; i < balls.length; i++) {
    for (let j = i + 1; j < balls.length; j++) {
      expect(Math.hypot(balls[i]!.x - balls[j]!.x, balls[i]!.y - balls[j]!.y)).toBeGreaterThan(2 * r - slack);
    }
  }
}

it("falls into a still pile at the bottom of the globe", () => {
  const drum = filled();
  drum.settle();
  expect(drum.settled).toBe(true);
  inside(drum);
  apart(drum);
  const mean = drum.balls.reduce((n, b) => n + b.y, 0) / drum.balls.length;
  expect(mean).toBeGreaterThan(drum.R * 0.25);
});

it("falls into the same pile every time", () => {
  const a = filled();
  const b = filled();
  a.settle();
  b.settle();
  expect(a.balls.map((x) => [x.x, x.y])).toEqual(b.balls.map((x) => [x.x, x.y]));
});

it("blows the balls about the globe while the air is on, and lets them settle again", () => {
  const drum = filled();
  drum.settle();
  drum.airTarget = 1;
  let upper = 0;
  let samples = 0;
  let turned = 0;
  for (let s = 0; s < 3; s += STEP * 4) {
    drum.update(STEP * 4);
    if (s < 0.6) continue;
    for (const b of drum.balls) {
      samples++;
      if (b.y < 0) upper++;
    }
  }
  turned = drum.balls.reduce((n, b) => n + Math.abs(b.a), 0);
  inside(drum);
  // A good share of the time in the upper half, and they spin as they go.
  expect(upper / samples).toBeGreaterThan(0.3);
  expect(turned).toBeGreaterThan(10);
  drum.airTarget = 0;
  for (let s = 0; s < 6 && !drum.settled; s += STEP) drum.update(STEP);
  expect(drum.settled).toBe(true);
  inside(drum);
});

it("pulls a ball out through the outlet", () => {
  const drum = filled();
  drum.settle();
  drum.airTarget = 1;
  drum.update(1);
  let out: string | null = null;
  expect(drum.pull("4", (b) => (out = b.d))).toBe(true);
  for (let s = 0; s < 2 && !out; s += STEP) drum.update(STEP);
  expect(out).toBe("4");
  expect(drum.has("4")).toBe(false);
  expect(drum.balls).toHaveLength(9);
  expect(drum.pull("4", () => {})).toBe(false);
});

it("hands its balls, its air and a pull still waiting to a resized globe, whose pull then completes", () => {
  const drum = filled();
  drum.settle();
  drum.remove("3");
  drum.airTarget = 1;
  for (let i = 0; i < 30; i++) drum.update(STEP);
  let out = "";
  expect(drum.pull("5", (b) => { out = b.d; })).toBe(true);
  const next = new Drum(52, 10.5, (38 * Math.PI) / 180);
  drum.handOver(next);
  expect(drum.balls).toEqual([]);
  expect(drum.pulling).toBe(false);
  expect(next.has("3")).toBe(false);
  expect(next.balls).toHaveLength(9);
  expect(next.airTarget).toBe(1);
  expect(next.pulling).toBe(true);
  for (let i = 0; i < 240 && !out; i++) next.update(STEP);
  expect(out).toBe("5");
  expect(next.has("5")).toBe(false);
});

it("lets a ball still being pulled leave at once when the globe goes away", () => {
  const drum = filled();
  drum.settle();
  let out = "";
  drum.pull("7", (b) => { out = b.d; });
  drum.release();
  expect(out).toBe("7");
  expect(drum.has("7")).toBe(false);
  expect(drum.pulling).toBe(false);
});
