// The stage under the photocards' page, as the page comes and goes: whoever came for it gives it back, a visit that
// leaves while it loads included, and the stage is taken down a while after the last one left.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createRenderer, h, ref, ssrContextKey } from "vue";

const io = vi.hoisted(() => ({
  /** Pictures wait for this; null: they come at once. */
  ready: null as null | Promise<void>,
  /** Pictures fail. */
  broken: false,
  fetched: 0, uploaded: 0, deleted: 0, lost: 0, frames: 0,
}));
vi.mock("../../photo/gl", async (actual) => ({
  ...await actual<typeof import("../../photo/gl")>(),
  picture: async () => {
    io.fetched++;
    await io.ready;
    if (io.broken) throw new Error("no picture");
    return { width: 4, height: 4, close() {} };
  },
  texture: () => { io.uploaded++; return {}; },
  grid: () => ({ draw() {}, dispose() {} }),
  startProgram: () => ({ ready: Promise.resolve(), use() {}, tex() {}, set() {}, dispose() {} }),
}));
const reduced = ref(false);
vi.mock("../../composables/usePageActive", () => ({ usePageActive: () => ref(true) }));
vi.mock("../../stores/ui", () => ({ ground: {} }));
vi.mock("../../stores/theme", () => ({ reducedMotion: reduced }));
vi.mock("./shop", () => ({
  groundFoot: ref(null), groundKind: ref(null), groundRose: ref(0), groundTitle: ref(null), groundUp: ref(false),
  openPage() {}, photoOver: ref(null), photoRun: ref(null), poster: ref(""), shopSeries: ref("asoul2026"),
}));

/** The canvas of the stage is in this host. */
interface Host { canvas: unknown }
const hosts: Host[] = [];
function element(): Host & Record<string, unknown> {
  const el = {
    canvas: null as unknown, clientWidth: 1000, clientHeight: 720, style: {},
    closest: () => null, getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 720 }),
    append(c: { parent?: unknown }) { el.canvas = c; c.parent = el; },
  };
  hosts.push(el);
  return el;
}
const canvas = {
  style: {}, width: 0, height: 0, parent: null as null | Host, addEventListener() {},
  remove() { if (canvas.parent) canvas.parent.canvas = null; canvas.parent = null; },
  getContext: () => new Proxy({ getExtension: () => ({ loseContext: () => { io.lost++; } }), deleteTexture: () => { io.deleted++; } }, {
    get: (target, k) => (k in target ? target[k as keyof typeof target] : () => {}),
  }),
};
const renderer = createRenderer<Host & Record<string, unknown>, Host & Record<string, unknown>>({
  createElement: element, createComment: () => ({}) as never, createText: () => ({}) as never, insert() {}, remove() {},
  patchProp() {}, setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null,
});

/** A visit of the photocards' page. */
async function visit() {
  const Backdrop = (await import("./PhotoBackdrop.vue")).default;
  const app = renderer.createApp({ ...Backdrop, render: () => h("div", { ref: "host" }) }, { on: true });
  app.provide(ssrContextKey, { modules: new Set() });
  app.mount(element());
  await vi.advanceTimersByTimeAsync(50);
  return app;
}
const shown = () => hosts.filter((el) => el.canvas).length;

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetModules();
  Object.assign(io, { ready: null, broken: false, fetched: 0, uploaded: 0, deleted: 0, lost: 0, frames: 0 });
  hosts.length = 0;
  reduced.value = false;
  canvas.parent = null;
  vi.stubGlobal("window", globalThis);
  vi.stubGlobal("document", { createElement: () => canvas });
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("requestAnimationFrame", () => ++io.frames);
  vi.stubGlobal("cancelAnimationFrame", () => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the stage of the photocards' page", () => {
  it("is taken down a while after the page was left while it loaded, and loads nothing more onto it", async () => {
    let come!: () => void;
    io.ready = new Promise<void>((done) => { come = done; });
    const page = await visit();
    expect(io.fetched).toBe(21);
    page.unmount();
    come();
    await vi.advanceTimersByTimeAsync(44_000);
    expect([io.uploaded, io.lost]).toEqual([0, 0]);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(io.lost).toBe(1);
  });

  it("loads anew for a page that comes back after a load nobody waited for", async () => {
    let come!: () => void;
    io.ready = new Promise<void>((done) => { come = done; });
    (await visit()).unmount();
    come();
    await vi.advanceTimersByTimeAsync(5_000);
    const again = await visit();
    await vi.advanceTimersByTimeAsync(50);
    expect([shown(), io.uploaded, io.lost]).toEqual([1, 21, 0]);
    again.unmount();
  });

  it("stays for the page that came back while it loaded", async () => {
    let come!: () => void;
    io.ready = new Promise<void>((done) => { come = done; });
    const first = await visit();
    first.unmount();
    const again = await visit();
    come();
    await vi.advanceTimersByTimeAsync(50);
    expect(shown()).toBe(1);
    expect(hosts.at(-1)!.canvas).toBe(canvas);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(io.lost).toBe(0);
    expect(io.uploaded).toBeGreaterThanOrEqual(21);
    again.unmount();
    await vi.advanceTimersByTimeAsync(46_000);
    expect(io.lost).toBe(1);
  });

  it("is not given up by a visit that left before a later one came", async () => {
    const first = await visit();
    expect(shown()).toBe(1);
    first.unmount();
    expect(shown()).toBe(0);
    await vi.advanceTimersByTimeAsync(20_000);
    const again = await visit();
    expect(shown()).toBe(1);
    // The first visit's time is up: the second still has it.
    await vi.advanceTimersByTimeAsync(60_000);
    expect([io.lost, shown()]).toEqual([0, 1]);
    again.unmount();
    await vi.advanceTimersByTimeAsync(46_000);
    expect(io.lost).toBe(1);
  });

  it("is taken down a while after it could not be loaded", async () => {
    io.broken = true;
    const page = await visit();
    await vi.advanceTimersByTimeAsync(46_000);
    expect(io.lost).toBe(1);
    page.unmount();
  });
});

describe("the stage with reduced motion", () => {
  it("is the still key visual: nothing of the stage is loaded or drawn", async () => {
    reduced.value = true;
    const shop = await import("./shop");
    const page = await visit();
    await vi.advanceTimersByTimeAsync(60_000);
    expect([io.fetched, io.uploaded, io.frames, shown()]).toEqual([0, 0, 0, 0]);
    expect(shop.groundUp.value).toBe(true);
    page.unmount();
  });

  it("comes and goes as motion is turned on and off", async () => {
    reduced.value = true;
    const page = await visit();
    reduced.value = false;
    await vi.advanceTimersByTimeAsync(50);
    expect([io.uploaded, shown()]).toEqual([21, 1]);
    reduced.value = true;
    await vi.advanceTimersByTimeAsync(50);
    expect(shown()).toBe(0);
    await vi.advanceTimersByTimeAsync(46_000);
    expect(io.lost).toBe(1);
    page.unmount();
  });
});
