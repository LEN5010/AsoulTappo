import { afterEach, beforeEach, expect, it, vi } from "vitest";

type Handler = (event: { payload: unknown }) => unknown;
const bus = vi.hoisted(() => ({ listeners: new Map<string, Set<Handler>>() }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (event: string, cb: Handler, options: { target: string }) => {
    const key = `${options.target}:${event}`;
    const listeners = bus.listeners.get(key) ?? new Set<Handler>();
    listeners.add(cb);
    bus.listeners.set(key, listeners);
    return () => listeners.delete(cb);
  }),
  emitTo: vi.fn(async (target: string, event: string, payload: unknown) => {
    const copy = JSON.parse(JSON.stringify(payload));
    await Promise.all([...bus.listeners.get(`${target}:${event}`) ?? []].map((cb) => cb({ payload: copy })));
  }),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => {}) }));

let stops: (() => void)[] = [];
beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  bus.listeners.clear();
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, v: string) => saved.set(key, v) });
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(async () => {
  stops.forEach((stop) => stop());
  stops = [];
  await Promise.resolve();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function context(panel: boolean) {
  vi.resetModules();
  vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: panel ? "?window=panel" : "" } });
  const uiStore = await import("../stores/ui");
  if (panel) uiStore.ui.panelOpen = true;
  const bridge = await import("./bridge");
  stops.push(await bridge.initDesktop());
  return {
    settings: (await import("../stores/settings")).settings,
    player: await import("../stores/player"),
    room: await import("../stores/room"),
    counter: (await import("../stores/counter")).counter,
    pet: await import("../stores/pet"),
    ui: await import("../stores/ui"),
  };
}

it("mirrors desk state and exchanges setting edits without starting panel requests", async () => {
  const desk = await context(false);
  desk.counter.total = 42;
  const panel = await context(true);
  expect(panel.counter.total).toBe(42);
  panel.settings.character = "贝拉";
  panel.settings.favorites.push("example");
  expect(desk.settings.character).toBe("贝拉");
  expect(desk.settings.favorites).toEqual(["example"]);
  desk.settings.clickThrough = true;
  expect(panel.settings.clickThrough).toBe(true);
  desk.counter.total++;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.counter.total).toBe(43);
  expect(fetch).not.toHaveBeenCalled();
});

it("applies action results to both windows before resolving an awaited draw", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const drops = [{ item: "card:test", new: true }] as Awaited<ReturnType<typeof desk.player.resonate>>;
  vi.spyOn(desk.player, "resonate").mockImplementation(async () => {
    desk.player.collection.owned["card:test"] = 1;
    return drops;
  });
  expect(await panel.player.resonate(1)).toEqual(drops);
  expect(desk.player.resonate).toHaveBeenCalledWith(1);
  expect(panel.player.collection.owned["card:test"]).toBe(1);
});

it("mirrors remote pet animation poses into the panel without another room socket", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  desk.room.members.set('friend', { id: 'friend', nick: '朋友', character: '乃琳', taps: 5, plate: 'c1',
    pulse: 0, emote: null, combo: null, motion: { dx: 8, dy: -4, keyDown: true, left: true, right: false } });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get('friend')!.motion).toEqual({ dx: 8, dy: -4, keyDown: true, left: true, right: false });
  expect(panel.room.members.get('friend')!.plate).toBe('c1');
  Object.assign(desk.room.members.get('friend')!.motion, { dx: 0, dy: 0, keyDown: false, left: false });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get('friend')!.motion.left).toBe(false);
  expect(fetch).not.toHaveBeenCalled();
});

it("counts input only in the desk while the panel preview reacts to the same key", async () => {
  const desk = await context(false);
  const panel = await context(true);
  desk.pet.onInput({ kind: "key_down" });
  panel.pet.onInput({ kind: "key_down" }, false);
  await vi.advanceTimersByTimeAsync(50);
  expect(desk.counter.total).toBe(1);
  expect(panel.counter.total).toBe(1);
  expect(panel.pet.pet.keyDown).toBe(true);
  expect(fetch).not.toHaveBeenCalled();
});

it("opens the regular panel while the pet is click-through and closes it separately", async () => {
  const desk = await context(false);
  const { invoke } = await import("@tauri-apps/api/core");
  desk.settings.clickThrough = true;
  desk.ui.openPanel("resonance");
  expect(invoke).toHaveBeenCalledWith("open_panel", { page: "resonance", craftTarget: "" });
  const panel = await context(true);
  expect(panel.ui.ui.page).toBe("resonance");
  panel.ui.closePanel();
  expect(invoke).toHaveBeenCalledWith("hide_panel");
  expect(desk.settings.clickThrough).toBe(true);
  expect(desk.settings.alwaysOnTop).toBe(true);
});

it("sends changed member runtime without replacing the collection, and resyncs after hiding", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  desk.room.members.set("friend", { id: "friend", nick: "朋友", character: "乃琳", taps: 1,
    pulse: 0, emote: null, combo: null, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
  await vi.advanceTimersByTimeAsync(50);
  const owned = panel.player.collection.owned;
  const { emitTo } = await import("@tauri-apps/api/event");
  vi.mocked(emitTo).mockClear();
  desk.room.members.get("friend")!.motion.dx = 7;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get("friend")!.motion.dx).toBe(7);
  expect(panel.player.collection.owned).toBe(owned);
  expect(emitTo).not.toHaveBeenCalledWith("panel", "desktop:state", expect.anything());
  panel.ui.ui.panelOpen = false;
  await vi.advanceTimersByTimeAsync(0);
  vi.mocked(emitTo).mockClear();
  desk.counter.total = 99;
  desk.room.members.get("friend")!.motion.dx = 13;
  await vi.advanceTimersByTimeAsync(200);
  expect(emitTo).not.toHaveBeenCalledWith("panel", "desktop:motion", expect.anything());
  expect(panel.counter.total).not.toBe(99);
  panel.ui.ui.panelOpen = true;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.counter.total).toBe(99);
  expect(panel.room.members.get("friend")!.motion.dx).toBe(13);
});
