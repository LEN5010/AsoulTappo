// The frames of the shared canvas: one a tick, whatever happens inside it.
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./gl", () => ({ context: () => ({}) }));
vi.mock("./kit", () => ({ createKit: () => ({ ready: compiled() }) }));
vi.mock("./painter", () => ({ createPainter: () => ({}) }));

/** The programs of the next canvas. */
let compiled = () => Promise.resolve();
/** Tell the canvases that they are lost, and the views that their size has changed. */
let lose: (() => void)[] = [];
let resized: (() => void)[] = [];

type Frame = (now: number) => void;
let queue = new Map<number, Frame>();
let ids = 0;
let now = 0;
/** One tick of the screen. */
function tick(ms = 16): void {
  now += ms;
  const due = queue;
  queue = new Map();
  for (const f of due.values()) f(now);
}

const host = (more = {}) => ({ clientWidth: 100, clientHeight: 80, append() {}, prepend() {}, ...more }) as unknown as HTMLElement;
const scene = (o: { busy?: boolean; update?: () => void } = {}) => ({
  busy: true, draws: 0, updates: 0, dpr: 0, ...o,
  resize(_w: number, _h: number, dpr: number) { this.dpr = dpr; },
  update() { this.updates++; o.update?.(); },
  draw() { this.draws++; },
});

async function engine() {
  vi.resetModules();
  const m = await import("./engine");
  await m.photoGl();
  return m;
}

beforeEach(() => {
  queue = new Map();
  ids = 0;
  now = 0;
  compiled = () => Promise.resolve();
  lose = [];
  resized = [];
  vi.stubGlobal("requestAnimationFrame", (f: Frame) => { queue.set(++ids, f); return ids; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => { queue.delete(id); });
  vi.stubGlobal("ResizeObserver", class { constructor(told: () => void) { resized.push(told); } observe() {} disconnect() {} });
  vi.stubGlobal("window", { devicePixelRatio: 1 });
  vi.stubGlobal("document", {
    createElement: () => ({
      style: {}, width: 0, height: 0, remove() {}, getContext: () => ({ drawImage() {} }),
      addEventListener(_: string, told: (e: object) => void) { lose.push(() => told({ preventDefault() {} })); },
    }),
  });
});

describe("the frames of the photocards' canvas", () => {
  it("draws once a tick, however often it is woken in the middle of one", async () => {
    const { mountScene } = await engine();
    const s = scene({ update: () => { mount.wake(); mount.wake(); } });
    const mount = mountScene(host(), s);
    for (let i = 0; i < 20; i++) tick();
    expect(s.updates).toBe(20);
    expect(queue.size).toBe(1);
  });

  it("stops when nothing moves, and goes on when it is woken", async () => {
    const { mountScene } = await engine();
    const s = scene();
    const mount = mountScene(host(), s);
    tick();
    s.busy = false;
    tick();
    expect(queue.size).toBe(0);
    mount.wake();
    mount.wake();
    expect(queue.size).toBe(1);
    tick();
    expect(queue.size).toBe(0);
    expect(s.updates).toBe(3);
  });

  it("takes one more frame for what woke it in the middle of the last", async () => {
    const { mountScene } = await engine();
    let once = true;
    const s = scene({ busy: false, update: () => { if (once) { once = false; mount.wake(); } } });
    const mount = mountScene(host(), s);
    for (let i = 0; i < 5; i++) tick();
    expect(s.updates).toBe(2);
  });

  it("hands the frames over when another view is mounted or released in the middle of one", async () => {
    const { mountScene } = await engine();
    const over = scene();
    let cover: ReturnType<typeof mountScene> | undefined;
    const under = scene({ update: () => { cover ??= mountScene(host(), over, { layer: 1 }); } });
    const back = mountScene(host(), under);
    tick();
    for (let i = 0; i < 4; i++) tick();
    expect([under.updates, over.updates, queue.size]).toEqual([1, 4, 1]);
    const leave = scene({ update: () => cover!.release() });
    cover!.swap(leave);
    tick();
    for (let i = 0; i < 3; i++) tick();
    expect([under.updates, leave.updates, queue.size]).toEqual([4, 1, 1]);
    back.show(false);
    expect(queue.size).toBe(0);
  });

  it("is not stuck after a scene throws", async () => {
    const { mountScene } = await engine();
    let bad = true;
    const s = scene({ update: () => { if (bad) throw new Error("once"); } });
    const mount = mountScene(host(), s);
    expect(() => tick()).toThrow("once");
    bad = false;
    mount.wake();
    tick();
    tick();
    expect([s.updates, queue.size]).toEqual([3, 1]);
  });

  it("draws smaller while that makes slow frames quicker", async () => {
    const { mountScene } = await engine();
    const s = scene();
    mountScene(host(), s);
    for (let i = 0; i < 60; i++) tick(40);
    expect(s.dpr).toBeCloseTo(0.8);
    for (let i = 0; i < 60; i++) tick(30);
    expect(s.dpr).toBeCloseTo(0.6);
    for (let i = 0; i < 200; i++) tick(29);
    expect(s.dpr).toBeCloseTo(0.6);
    for (let i = 0; i < 200; i++) tick(22);
    expect(s.dpr).toBeCloseTo(0.6);
  });

  it("goes back to full size where frames stay as far apart", async () => {
    const { mountScene } = await engine();
    const s = scene();
    mountScene(host(), s);
    for (let i = 0; i < 60; i++) tick(33.4);
    expect(s.dpr).toBeCloseTo(0.8);
    for (let i = 0; i < 400; i++) tick(33.4);
    expect(s.dpr).toBeCloseTo(1);
  });

  it("goes back to full size once frames have been quick for a few seconds", async () => {
    const { mountScene } = await engine();
    const s = scene();
    mountScene(host(), s);
    for (let i = 0; i < 45; i++) tick(40);
    for (let i = 0; i < 120; i++) tick(16.7);
    expect(s.dpr).toBeCloseTo(0.8);
    for (let i = 0; i < 240; i++) tick(16.7);
    expect(s.dpr).toBeCloseTo(1);
  });

  it("does not count on what it saw before another view came", async () => {
    const { mountScene } = await engine();
    const s = scene(), over = scene();
    mountScene(host(), s);
    for (let i = 0; i < 60; i++) tick(33.4);
    expect(s.dpr).toBeCloseTo(0.8);
    const cover = mountScene(host(), over, { layer: 1 });
    expect(over.dpr).toBeCloseTo(1);
    for (let i = 0; i < 400; i++) tick(33.4);
    cover.release();
    expect([over.dpr, s.dpr].map((v) => v.toFixed(2))).toEqual(["1.00", "1.00"]);
  });

  it("keeps a picture of a view that another covers, seen or not", async () => {
    const { mountScene } = await engine();
    const stills: object[] = [];
    mountScene(host({ prepend: (c: object) => stills.push(c) }), scene()).show(false);
    mountScene(host(), scene(), { layer: 2 });
    expect(stills.length).toBe(1);
  });

  it("draws a view again when its size changes, seen or not", async () => {
    const { mountScene } = await engine();
    const s = scene(), place = { clientWidth: 100 }, h = host();
    Object.defineProperty(h, "clientWidth", { get: () => place.clientWidth });
    mountScene(h, s).show(false);
    const { draws } = s;
    place.clientWidth = 120;
    resized.forEach((told) => told());
    expect(s.draws).toBe(draws + 1);
    expect(queue.size).toBe(0);
  });
});

describe("the shared canvas", () => {
  it("is made anew after it could not be made", async () => {
    vi.resetModules();
    const { photoGl } = await import("./engine");
    compiled = () => Promise.reject(new Error("once"));
    expect(await photoGl()).toBeNull();
    compiled = () => Promise.resolve();
    expect(await photoGl()).not.toBeNull();
  });

  it("is the one made after another was lost, though that one fails later", async () => {
    vi.resetModules();
    const { photoGl } = await import("./engine");
    let fail = () => {}, done = () => {};
    compiled = () => new Promise((_, no) => { fail = () => no(new Error("lost")); });
    const first = photoGl();
    lose[0]();
    compiled = () => new Promise((ok) => { done = ok; });
    const second = photoGl();
    fail();
    expect(await first).toBeNull();
    done();
    expect(await second).not.toBeNull();
    expect(await photoGl()).toBe(await second);
  });
});
