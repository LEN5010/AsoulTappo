import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MotionFrames } from "./MotionFrames";
import { restingMotion, type PetMotion } from "./protocol";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

/** Frames come 16ms after they are asked for, on the fake clock that also runs the press timer. */
function setup() {
  const requested = vi.fn();
  let waiting = 0;
  const frames = new MotionFrames(
    (cb) => { requested(); waiting++; return setTimeout(() => { waiting--; cb(0); }, 16) as unknown as number; },
    (id) => { waiting--; clearTimeout(id); },
    () => Date.now(),
  );
  return { frames, requested, idle: () => waiting === 0 && vi.getTimerCount() === 0 };
}
const painter = () => {
  const shown: PetMotion[] = [];
  return { shown, paint: (pose: PetMotion) => shown.push({ ...pose }), last: () => shown.at(-1)! };
};

it("paints everything heard within a frame once, and nothing runs between updates", () => {
  const { frames, requested, idle } = setup();
  const a = painter(), b = painter();
  frames.update("a", { ...restingMotion(), dx: 4 });
  frames.subscribe("a", a.paint);
  frames.subscribe("b", b.paint);
  // A painter starts on the pose held.
  expect(a.shown).toEqual([{ ...restingMotion(), dx: 4 }]);
  expect(b.shown).toEqual([restingMotion()]);
  expect(idle()).toBe(true);
  for (let dx = 1; dx <= 5; dx++) {
    frames.update("a", { ...restingMotion(), dx });
    frames.update("b", { ...restingMotion(), dx: -dx, dy: 2 });
  }
  expect(requested).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(16);
  expect(a.shown).toHaveLength(2);
  expect(a.last()).toEqual({ ...restingMotion(), dx: 5 });
  expect(b.last()).toEqual({ ...restingMotion(), dx: -5, dy: 2 });
  // The glide to that pose is the stylesheet's: no frame, no timer.
  expect(idle()).toBe(true);
  vi.advanceTimersByTime(1000);
  expect(a.shown).toHaveLength(2);
});

it("keeps a press shorter than a frame down for 70ms, and dips the keyboard paw for a tap", () => {
  const { frames, idle } = setup();
  const p = painter();
  frames.subscribe("a", p.paint);
  frames.update("a", { ...restingMotion(), left: true });
  frames.update("a", restingMotion());
  vi.advanceTimersByTime(16);
  expect(p.last().left).toBe(true);
  vi.advanceTimersByTime(40);
  expect(p.last().left).toBe(true);
  vi.advanceTimersByTime(40);
  expect(p.last().left).toBe(false);
  expect(idle()).toBe(true);
  // A press held longer than that is let go as soon as the release is heard.
  frames.update("a", { ...restingMotion(), right: true });
  vi.advanceTimersByTime(200);
  frames.update("a", restingMotion());
  vi.advanceTimersByTime(16);
  expect(p.last().right).toBe(false);
  expect(idle()).toBe(true);
  frames.pulse("a");
  vi.advanceTimersByTime(16);
  expect(p.last().keyDown).toBe(true);
  vi.advanceTimersByTime(80);
  expect(p.last().keyDown).toBe(false);
  expect(idle()).toBe(true);
});

it("ends presses that began at different times each in its turn", () => {
  const { frames, idle } = setup();
  const a = painter(), b = painter();
  frames.subscribe("a", a.paint);
  frames.subscribe("b", b.paint);
  frames.update("a", { ...restingMotion(), keyDown: true });
  frames.update("a", restingMotion());
  vi.advanceTimersByTime(40);
  frames.update("b", { ...restingMotion(), keyDown: true });
  frames.update("b", restingMotion());
  vi.advanceTimersByTime(16);
  expect([a.last().keyDown, b.last().keyDown]).toEqual([true, true]);
  vi.advanceTimersByTime(34);
  expect([a.last().keyDown, b.last().keyDown]).toEqual([false, true]);
  vi.advanceTimersByTime(60);
  expect([a.last().keyDown, b.last().keyDown]).toEqual([false, false]);
  expect(idle()).toBe(true);
});

it("reports the pets being painted, and paints nothing for the others", () => {
  const { frames, requested, idle } = setup();
  const interest = vi.fn();
  frames.onInterest(interest);
  expect(interest).toHaveBeenLastCalledWith([]);
  const a = painter(), again = painter();
  const stopA = frames.subscribe("a", a.paint);
  const stopAgain = frames.subscribe("a", again.paint);
  expect(interest).toHaveBeenCalledTimes(2);
  expect(interest).toHaveBeenLastCalledWith(["a"]);
  // An update for a pet nobody draws is kept for later and asks for no frame.
  const heard = vi.fn();
  frames.onUpdate(heard);
  frames.update("b", { ...restingMotion(), dx: 3 });
  expect(heard).toHaveBeenCalledWith("b", { ...restingMotion(), dx: 3 }, false);
  expect(requested).not.toHaveBeenCalled();
  stopA();
  expect(interest).toHaveBeenCalledTimes(2);
  frames.update("a", { ...restingMotion(), dx: 1 });
  stopAgain();
  // The last painter leaving cancels the frame it was waiting for.
  expect(idle()).toBe(true);
  expect(interest).toHaveBeenLastCalledWith([]);
  const b = painter();
  frames.subscribe("b", b.paint);
  expect(b.last().dx).toBe(3);
});

it("reports every button edge immediately while identifying coordinate-only updates", () => {
  const { frames } = setup();
  const heard = vi.fn();
  frames.onUpdate(heard);
  const moving = { ...restingMotion(), dx: 3 };
  frames.update("a", moving);
  frames.update("a", { ...moving, left: true });
  frames.update("a", moving);
  expect(heard.mock.calls).toEqual([
    ["a", moving, false],
    ["a", { ...moving, left: true }, true],
    ["a", moving, true],
  ]);
});
