import { afterEach, beforeEach, expect, it, vi } from "vitest";

const native = vi.hoisted(() => ({ visible: undefined as ((event: { payload: boolean }) => void) | undefined, shown: true }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (_event: string, cb: (event: { payload: boolean }) => void) => { native.visible = cb; return () => {}; }),
}));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ isVisible: async () => native.shown }) }));

function loop(iterations: number) {
  const animation = {
    playState: "running", effect: { getComputedTiming: () => ({ iterations }) },
    pause: vi.fn(() => { animation.playState = "paused"; }), play: vi.fn(() => { animation.playState = "running"; }),
  };
  return animation;
}

async function start(panel: boolean, animations: ReturnType<typeof loop>[] = []) {
  vi.resetModules();
  const listeners = new Map<string, () => void>();
  vi.stubGlobal("window", {
    __TAURI_INTERNALS__: {}, location: { search: panel ? "?window=panel" : "" },
    addEventListener: (event: string, cb: () => void) => listeners.set(event, cb), removeEventListener: () => {},
  });
  // createElement: Vue's DOM runtime makes a template element as soon as it finds a document.
  const doc = { hidden: false, getAnimations: () => animations, createElement: () => ({}), addEventListener: (event: string, cb: () => void) => listeners.set(event, cb),
    removeEventListener: () => {} };
  vi.stubGlobal("document", doc);
  const activity = await import("./activity");
  const stop = await activity.startActivity();
  return { activity, stop, doc, fire: (event: string) => listeners.get(event)!() };
}

beforeEach(() => { vi.useFakeTimers(); native.shown = true; native.visible = undefined; });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("lets the desk's loops run until nothing has happened for half a minute, and again from the next event", async () => {
  const endless = loop(Infinity), once = loop(1);
  const { activity, stop } = await start(false, [endless, once]);
  expect(activity.renderActive.value).toBe(true);
  await vi.advanceTimersByTimeAsync(20_000);
  activity.noteActivity();
  await vi.advanceTimersByTimeAsync(29_000);
  expect(activity.renderActive.value).toBe(true);
  await vi.advanceTimersByTimeAsync(1_000);
  expect(activity.renderActive.value).toBe(false);
  // Still on screen: pets keep being drawn from what the room sends.
  expect(activity.windowVisible.value).toBe(true);
  expect(endless.pause).toHaveBeenCalledTimes(1);
  expect(once.pause).not.toHaveBeenCalled();
  // No timer runs while idle.
  expect(vi.getTimerCount()).toBe(0);
  activity.noteActivity();
  await vi.advanceTimersByTimeAsync(0);
  expect(activity.renderActive.value).toBe(true);
  expect(endless.play).toHaveBeenCalledTimes(1);
  stop();
});

it("follows the pet being hidden and shown, and counts nothing as activity while hidden", async () => {
  const { activity, stop, doc, fire } = await start(false);
  native.visible!({ payload: false });
  expect(activity.windowVisible.value).toBe(false);
  expect(vi.getTimerCount()).toBe(0);
  activity.noteActivity();
  expect(vi.getTimerCount()).toBe(0);
  native.visible!({ payload: true });
  expect(activity.renderActive.value).toBe(true);
  doc.hidden = true;
  fire("visibilitychange");
  expect(activity.windowVisible.value).toBe(false);
  stop();
});

it("starts hidden when the pet was hidden before the page loaded", async () => {
  native.shown = false;
  const { activity, stop } = await start(false);
  expect(activity.windowVisible.value).toBe(false);
  stop();
});

it("never idles the panel: a card video may be watched hands off", async () => {
  const { activity, stop } = await start(true);
  await vi.advanceTimersByTimeAsync(120_000);
  expect(activity.renderActive.value).toBe(true);
  expect(native.visible).toBeUndefined();
  stop();
});
