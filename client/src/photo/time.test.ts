import { describe, expect, it } from "vitest";
import { createTimeline, E } from "./time";

/** Lets what promises have queued run. */
const settle = () => new Promise<void>((done) => setTimeout(done));

describe("the timeline", () => {
  it("brings a number to its end, no further, and then resolves", async () => {
    const time = createTimeline();
    const o = { x: 10, y: 1 };
    let done = false;
    void time.tween(o, { x: 110 }, 400, E.flow).then(() => { done = true; });
    let last = o.x;
    for (let t = 0; t < 384; t += 16) {
      time.advance(16);
      expect(o.x).toBeGreaterThanOrEqual(last);
      last = o.x;
    }
    await settle();
    expect(done).toBe(false);
    time.advance(16);
    expect(o).toEqual({ x: 110, y: 1 });
    await settle();
    expect(done).toBe(true);
    expect(time.busy).toBe(false);
    time.advance(1000);
    expect(o.x).toBe(110);
    expect(time.clock).toBe(1400);
  });

  it("starts from where a thing is when its delay is over", () => {
    const time = createTimeline();
    const o = { x: 0 };
    void time.tween(o, { x: 100 }, 100, E.linear, 160);
    for (let t = 0; t < 144; t += 16) time.advance(16);
    expect(o.x).toBe(0);
    o.x = 50;
    time.advance(16);
    expect(o.x).toBe(50);
    time.advance(50);
    expect(o.x).toBe(75);
  });

  it("lets a later move of the same number take over at the speed it had", () => {
    const time = createTimeline();
    const o = { x: 0, y: 0 }, dt = 4;
    /** Pixels a millisecond over the next step. */
    const speed = () => {
      const { x } = o;
      time.advance(dt);
      return (o.x - x) / dt;
    };
    void time.tween(o, { x: 300, y: 80 }, 800, E.flow);
    while (time.clock < 400) time.advance(dt);
    const before = speed();
    void time.tween(o, { x: -100 }, 800, E.flow);
    let last = before;
    for (let k = 0; k < 8; k++) {
      const now = speed();
      expect(Math.abs(now - last)).toBeLessThan(before * 0.12);
      last = now;
    }
    expect(last).toBeGreaterThan(0);       // it goes on the way it went before it turns back
    while (time.busy) time.advance(dt);
    expect(o.x).toBe(-100);
    expect(o.y).toBe(80);                  // the first move kept the number nobody else asked for
  });

  it("takes one step while a move changes over to the next, whenever that one begins", () => {
    for (const late of [0, 3, 8, 13, 16]) {
      const time = createTimeline();
      const o = { x: 0 }, dt = 16, steps: number[] = [];
      void time.tween(o, { x: 3000 }, 1000, E.linear);
      for (let k = 0; k < 20; k++) time.advance(dt);
      void time.tween(o, { x: 1200 }, 600, E.flow, late);
      for (let k = 0; k < 4; k++) {
        const { x } = o;
        time.advance(dt);
        steps.push(o.x - x);
      }
      let last = 3 * dt;
      for (const s of steps) {
        expect(s).toBeGreaterThan(last * 0.75);
        expect(s).toBeLessThan(last * 1.001);
        last = s;
      }
    }
  });

  it("starts a move from rest on a thing that stands still", () => {
    const time = createTimeline();
    const o = { x: 0 };
    void time.tween(o, { x: 100 }, 200, E.flow);
    while (time.busy) time.advance(16);
    void time.tween(o, { x: 0 }, 200, E.flow);
    time.advance(1);
    expect(100 - o.x).toBeLessThan(0.01);
  });

  it("drops a move that has not begun for a later one of the same number", async () => {
    const time = createTimeline();
    const o = { x: 0 };
    void time.tween(o, { x: 500 }, 100, E.linear, 100);
    void time.tween(o, { x: 40 }, 100, E.linear);
    for (let t = 0; t < 400; t += 20) time.advance(20);
    expect(o.x).toBe(40);
    expect(time.busy).toBe(false);
  });

  it("moves numbers a thing has not got yet from 0", () => {
    const time = createTimeline();
    const o: { x?: number } = {};
    void time.tween(o, { x: 10 }, 100, E.linear);
    time.advance(50);
    expect(o.x).toBe(5);
  });

  it("resolves waits in the order they are over", async () => {
    const time = createTimeline();
    const order: string[] = [];
    void time.wait(90).then(() => order.push("c"));
    void time.wait(30).then(() => order.push("a"));
    void time.wait(60).then(() => order.push("b"));
    for (let t = 0; t < 96; t += 16) {
      time.advance(16);
      await settle();
    }
    expect(order).toEqual(["a", "b", "c"]);
  });

  it("goes on from one wait to the next within a run", async () => {
    const time = createTimeline();
    const at: number[] = [];
    const run = async () => {
      await time.wait(40);
      at.push(time.clock);
      await time.wait(40);
      at.push(time.clock);
    };
    void run();
    for (let t = 0; t < 160; t += 16) {
      time.advance(16);
      await settle();
    }
    expect(at).toEqual([48, 96]);
  });

  it("drops everything when cleared: nothing moves on, nothing resolves, no speed is kept", async () => {
    const time = createTimeline();
    const o = { x: 0 };
    let settled = 0;
    const count = () => { settled += 1; };
    void time.tween(o, { x: 100 }, 200, E.linear).then(count, count);
    void time.wait(120).then(count, count);
    time.advance(100);
    void time.tween(o, { x: 0 }, 200, E.linear, 500).then(count, count);
    const { x } = o;
    expect(x).toBe(50);
    time.clear();
    expect(time.busy).toBe(false);
    for (let t = 0; t < 1000; t += 20) time.advance(20);
    await settle();
    expect(o.x).toBe(x);
    expect(settled).toBe(0);
    expect(time.clock).toBe(1100);
    void time.tween(o, { x: 0 }, 400, E.flow);
    time.advance(1);
    expect(Math.abs(o.x - x)).toBeLessThan(0.01);
  });
});

describe("the easings", () => {
  it("run from 0 to 1 and never back", () => {
    for (const ease of Object.values(E)) {
      expect(ease(0)).toBeCloseTo(0, 12);
      expect(ease(1)).toBeCloseTo(1, 12);
      let last = 0;
      for (let t = 0.01; t <= 1; t += 0.01) {
        expect(ease(t)).toBeGreaterThanOrEqual(last);
        last = ease(t);
      }
    }
  });
});
