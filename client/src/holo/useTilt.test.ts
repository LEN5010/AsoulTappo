import { effectScope } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FLAT, MAX_TILT, tiltToward } from "./shader";
import { useTilt } from "./useTilt";

function fakeElement(rect = { left: 0, top: 0, width: 100, height: 150 }) {
  return { getBoundingClientRect: () => rect } as unknown as Element;
}

function fakePointer(clientX: number, clientY: number) {
  return { clientX, clientY } as PointerEvent;
}

describe("useTilt", () => {
  const frames = new Map<number, FrameRequestCallback>();
  let nextId = 0;
  let now = 0;

  function step(dt = 16) {
    now += dt;
    const queued = [...frames.values()];
    frames.clear();
    for (const cb of queued) cb(now);
  }

  beforeEach(() => {
    frames.clear();
    nextId = 0;
    now = 0;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      const id = ++nextId;
      frames.set(id, cb);
      return id;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      frames.delete(id);
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stops requestAnimationFrame once hover converges, then wakes on move or leave", () => {
    const onSettle = vi.fn();
    const scope = effectScope();
    const api = scope.run(() => useTilt(MAX_TILT, onSettle))!;
    const el = fakeElement();
    const target = tiltToward(0.9, 0.2, MAX_TILT);

    api.follow(fakePointer(90, 30), el);
    expect(api.lit.value).toBe(true);
    expect(api.moving.value).toBe(true);
    expect(frames.size).toBe(1);

    // Advance until hover converges (< 0.02 deg from target).
    for (let i = 0; i < 60 && frames.size > 0; i++) step(16);

    expect(frames.size).toBe(0);
    expect(api.tilt.value).toEqual(target);
    expect(api.lit.value).toBe(true);
    expect(api.moving.value).toBe(true);
    expect(onSettle).not.toHaveBeenCalled();

    // Moving the pointer to a new point wakes rAF and converges again.
    const nextTarget = tiltToward(0.1, 0.8, MAX_TILT);
    api.follow(fakePointer(10, 120), el);
    expect(frames.size).toBe(1);
    for (let i = 0; i < 60 && frames.size > 0; i++) step(16);
    expect(frames.size).toBe(0);
    expect(api.tilt.value).toEqual(nextTarget);
    expect(onSettle).not.toHaveBeenCalled();

    // Leaving wakes rAF, eases back to FLAT, and invokes onSettle once.
    api.leave();
    expect(api.lit.value).toBe(false);
    expect(frames.size).toBe(1);
    for (let i = 0; i < 200 && frames.size > 0; i++) step(16);

    expect(frames.size).toBe(0);
    expect(api.tilt.value).toEqual(FLAT);
    expect(api.moving.value).toBe(false);
    expect(onSettle).toHaveBeenCalledTimes(1);

    scope.stop();
  });

  it("asks for no more frames while the pointer rests on the card", () => {
    const scope = effectScope();
    const api = scope.run(() => useTilt(MAX_TILT))!;
    const el = fakeElement();
    api.follow(fakePointer(90, 30), el);
    let callbacks = 0;
    for (let i = 0; i < 600; i++) {
      if (frames.size) callbacks += 1;
      step(1000 / 60);
    }
    expect(callbacks).toBeLessThan(60);
    expect(frames.size).toBe(0);
    expect(api.tilt.value).toEqual(tiltToward(0.9, 0.2, MAX_TILT));
    // Pressed on the same spot again: nothing to move toward, at most one frame.
    api.follow(fakePointer(90, 30), el);
    step(16);
    expect(frames.size).toBe(0);
    scope.stop();
  });

  it("cancels pending frames immediately on reset without calling onSettle", () => {
    const onSettle = vi.fn();
    const scope = effectScope();
    const api = scope.run(() => useTilt(MAX_TILT, onSettle))!;
    api.follow(fakePointer(100, 0), fakeElement());
    step(16);
    expect(frames.size).toBe(1);

    api.reset();
    expect(frames.size).toBe(0);
    expect(api.tilt.value).toEqual(FLAT);
    expect(api.lit.value).toBe(false);
    expect(api.moving.value).toBe(false);
    expect(onSettle).not.toHaveBeenCalled();

    scope.stop();
  });
});
