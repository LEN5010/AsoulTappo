import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MotionSender } from "./MotionSender";
import { restingMotion } from "./protocol";
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("coalesces mouse frames, sends the final resting pose, and preserves short button presses", () => {
  const send = vi.fn();
  const sender = new MotionSender(send);
  sender.update(restingMotion());
  for (let i = 1; i <= 10; i++) sender.update({ ...restingMotion(), dx: i });
  expect(send).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(50);
  expect(send).toHaveBeenLastCalledWith({ ...restingMotion(), dx: 10 });
  sender.update({ ...restingMotion(), left: true });
  sender.update(restingMotion());
  expect(send.mock.calls.slice(-2).map(([pose]) => pose.left)).toEqual([true, false]);
  sender.update(restingMotion());
  vi.advanceTimersByTime(50);
  expect(send).toHaveBeenCalledTimes(4);
});

it("discards pending movement when leaving so a new room starts with its own pose", () => {
  const send = vi.fn();
  const sender = new MotionSender(send);
  sender.update(restingMotion());
  sender.update({ ...restingMotion(), dx: 7 });
  sender.clear();
  vi.advanceTimersByTime(100);
  expect(send).toHaveBeenCalledTimes(1);
  sender.update({ ...restingMotion(), keyDown: true });
  expect(send).toHaveBeenLastCalledWith({ ...restingMotion(), keyDown: true });
});
