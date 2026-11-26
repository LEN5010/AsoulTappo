import { afterEach, expect, it, vi } from "vitest";
import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";

// The stage's lifecycle, run by hand: there is no DOM here to mount it in.
const hooks = vi.hoisted(() => ({ mounted: [] as (() => void)[], activated: [] as (() => void)[], deactivated: [] as (() => void)[] }));
vi.mock("vue", async (original) => ({
  ...(await original<typeof import("vue")>()),
  onMounted: (fn: () => void) => hooks.mounted.push(fn),
  onActivated: (fn: () => void) => hooks.activated.push(fn),
  onDeactivated: (fn: () => void) => hooks.deactivated.push(fn),
  onBeforeUnmount: (fn: () => void) => hooks.deactivated.push(fn),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  hooks.mounted.length = hooks.activated.length = hooks.deactivated.length = 0;
});

async function stage() {
  let fontsReady!: () => void;
  const ready = new Promise<void>((done) => { fontsReady = done; });
  const frames: FrameRequestCallback[] = [];
  vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => frames.push(fn));
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("document", { fonts: { ready }, createRange: () => ({}) });
  const { default: PoolStage } = await import("./PoolStage.vue");
  // Set up inside a component, as the compiled stage asks for its rendering context.
  await renderToString(createSSRApp({
    setup() {
      PoolStage.setup!({ busy: false } as never, { emit() {}, expose() {}, attrs: {}, slots: {} } as never);
      return () => null;
    },
  }));
  hooks.mounted.forEach((fn) => fn());
  return { frames, fontsReady: async () => { fontsReady(); await ready; await Promise.resolve(); } };
}

it("measures again once the bundled font has loaded", async () => {
  const { frames, fontsReady } = await stage();
  expect(frames).toHaveLength(1);
  frames[0](0);
  await fontsReady();
  expect(frames).toHaveLength(2);
});

it("puts off no measuring for a font that loads after the stage was put away", async () => {
  const { frames, fontsReady } = await stage();
  expect(frames).toHaveLength(1);
  hooks.deactivated.forEach((fn) => fn());
  await fontsReady();
  expect(frames).toHaveLength(1);
});
