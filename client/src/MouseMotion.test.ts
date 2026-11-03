import { expect, it } from "vitest";
import { MouseMotion } from "./MouseMotion";

function setup() {
  const frames = new Map<number, () => void>();
  let id = 0;
  const position = { dx: 0, dy: 0 };
  const motion = new MouseMotion(position, (cb) => { frames.set(++id, cb); return id; }, (n) => { frames.delete(n); });
  const step = () => {
    const scheduled = [...frames.values()];
    frames.clear();
    scheduled.forEach((cb) => cb());
  };
  return { frames, motion, position, step };
}

it("stays idle, wakes once on movement and stops when visually settled", () => {
  const { frames, motion, position, step } = setup();
  expect(frames.size).toBe(0);
  motion.move(10, -5, .3);
  motion.move(5, 5, .3);
  expect(frames.size).toBe(1);
  step();
  expect(position.dx).toBeGreaterThan(0);
  for (let i = 0; i < 300; i++) step();
  expect(frames.size).toBe(0);
  expect(position).toEqual({ dx: 0, dy: 0 });
  motion.move(5, 0, .3);
  expect(frames.size).toBe(1);
});

it("cancels and centres when following is disabled or the app unmounts", () => {
  const { frames, motion, position, step } = setup();
  motion.move(100, 0, 1);
  step();
  motion.stop();
  step();
  expect(frames.size).toBe(0);
  expect(position).toEqual({ dx: 0, dy: 0 });
  motion.move(1000, 0, 1);
  expect(frames.size).toBe(0);
});
