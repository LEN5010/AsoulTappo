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
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(performance.now()), 16));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
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
    motion: (await import("../net/MotionFrames")).remoteMotion,
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

it("runs scratch card requests in the desk and mirrors the card on the table into the panel", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const card = { id: 5, cells: ["200"] };
  const buy = vi.spyOn(desk.player, "buyScratch").mockImplementation(async () => (desk.player.scratchCard.value = card));
  const load = vi.spyOn(desk.player, "loadScratch").mockImplementation(async () => { desk.player.scratchCard.value = card; });
  const reveal = vi.spyOn(desk.player, "revealScratch").mockImplementation(async () => {
    desk.player.scratchCard.value = null;
    return { shards: 200, item: null };
  });
  expect(await panel.player.buyScratch()).toEqual(card);
  expect(panel.player.scratchCard.value).toEqual(card);
  expect(await panel.player.revealScratch(5)).toEqual({ shards: 200, item: null });
  expect(reveal).toHaveBeenCalledWith(5);
  expect(panel.player.scratchCard.value).toBeNull();
  // Not asked while the status says nothing of scratch cards.
  await panel.player.loadScratch();
  expect(load).not.toHaveBeenCalled();
  desk.player.status.value = panel.player.status.value = {
    player: "p1", shards: 0, income: { multiplier: 1, perMinute: 0 },
    resonance: { pity: { legendary: 0, skin: 0 }, hardPity: { legendary: 90, skin: 200 }, total: 0 },
    totals: { taps: 0, activeMinutes: 0, owned: 0, items: 0 }, scratch: { left: 19, pity: 1 },
  };
  await panel.player.loadScratch();
  expect(panel.player.scratchCard.value).toEqual(card);
  expect(buy).toHaveBeenCalledTimes(1);
  expect(load).toHaveBeenCalledTimes(1);
  expect(fetch).not.toHaveBeenCalled();
});

it("mirrors remote pet animation poses into the panel without another room socket", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  const subscribed = vi.spyOn(desk.room, "setPanelMotionInterest");
  const resting = { dx: 0, dy: 0, keyDown: false, left: false, right: false };
  const pose = { dx: 8, dy: -4, keyDown: true, left: true, right: false };
  for (const id of ["friend", "unseen"]) {
    desk.room.members.set(id, { id, nick: '朋友', character: '乃琳', taps: 5, plate: 'c1',
      pulse: 0, emote: null, combo: null, win: null, motion: { ...pose } });
  }
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get('friend')!.plate).toBe('c1');
  // The panel draws no pet yet, so no pose has come over.
  expect(panel.room.members.get('friend')!.motion).toEqual(resting);
  const drawn: unknown[] = [];
  panel.motion.subscribe('friend', (shown) => drawn.push({ ...shown }));
  await vi.advanceTimersByTimeAsync(50);
  // Drawing one starts from the pose the desk holds, and the room is asked for that member's movement.
  expect(subscribed).toHaveBeenLastCalledWith(['friend']);
  expect(panel.room.members.get('friend')!.motion).toEqual(pose);
  expect(panel.room.members.get('unseen')!.motion).toEqual(resting);
  // The room's updates reach the panel's painter the way they reach the desk's.
  for (const id of ["friend", "unseen"]) {
    Object.assign(desk.room.members.get(id)!.motion, resting);
    desk.motion.update(id, resting);
  }
  await vi.advanceTimersByTimeAsync(200);
  expect(panel.room.members.get('friend')!.motion).toEqual(resting);
  expect(drawn.at(-1)).toEqual(resting);
  // Taps are counted for every member, drawn or not.
  desk.room.members.get('unseen')!.taps = 9;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get('unseen')!.taps).toBe(9);
  panel.ui.ui.page = "emotes";
  await vi.advanceTimersByTimeAsync(50);
  expect(subscribed).toHaveBeenLastCalledWith([]);
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

it.each(["keyDown", "left", "right"] as const)("shows a short remote %s press in the panel", async (button) => {
  vi.spyOn(performance, "now").mockImplementation(() => Date.now());
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  const resting = { dx: 0, dy: 0, keyDown: false, left: false, right: false };
  desk.room.members.set("friend", { id: "friend", nick: "朋友", character: "乃琳", taps: 0,
    pulse: 0, emote: null, combo: null, win: null, motion: { ...resting } });
  await vi.advanceTimersByTimeAsync(50);
  const drawn: boolean[] = [];
  stops.push(panel.motion.subscribe("friend", (pose) => drawn.push(pose[button])));
  await vi.advanceTimersByTimeAsync(50);
  desk.motion.update("friend", { ...resting, [button]: true });
  expect(panel.room.members.get("friend")!.motion[button]).toBe(true);
  await vi.advanceTimersByTimeAsync(5);
  desk.motion.update("friend", resting);
  expect(panel.room.members.get("friend")!.motion[button]).toBe(false);
  await vi.advanceTimersByTimeAsync(16);
  expect(drawn.at(-1)).toBe(true);
  await vi.advanceTimersByTimeAsync(100);
  expect(drawn.at(-1)).toBe(false);
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
    pulse: 0, emote: null, combo: null, win: null, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
  await vi.advanceTimersByTimeAsync(50);
  const owned = panel.player.collection.owned;
  const { emitTo } = await import("@tauri-apps/api/event");
  vi.mocked(emitTo).mockClear();
  panel.motion.subscribe("friend", () => {});
  await vi.advanceTimersByTimeAsync(50);
  const move = (dx: number) => {
    desk.room.members.get("friend")!.motion.dx = dx;
    desk.motion.update("friend", { ...desk.room.members.get("friend")!.motion });
  };
  move(7);
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get("friend")!.motion.dx).toBe(7);
  expect(panel.player.collection.owned).toBe(owned);
  expect(emitTo).not.toHaveBeenCalledWith("panel", "desktop:state", expect.anything());
  panel.ui.ui.panelOpen = false;
  await vi.advanceTimersByTimeAsync(0);
  vi.mocked(emitTo).mockClear();
  desk.counter.total = 99;
  move(13);
  await vi.advanceTimersByTimeAsync(200);
  expect(emitTo).not.toHaveBeenCalledWith("panel", "desktop:motion", expect.anything());
  expect(panel.counter.total).not.toBe(99);
  panel.ui.ui.panelOpen = true;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.counter.total).toBe(99);
  expect(panel.room.members.get("friend")!.motion.dx).toBe(13);
});

it("mirrors scratch card wins over partner pets and the own pet into the panel room", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  desk.room.members.set("friend", { id: "friend", nick: "朋友", character: "乃琳", taps: 0,
    pulse: 0, emote: null, combo: null, win: null, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
  await vi.advanceTimersByTimeAsync(50);
  desk.room.members.get("friend")!.win = { count: 2500, seq: 1, beat: 1 };
  desk.room.localPet.win = { count: 30000, seq: 1, beat: 1 };
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.get("friend")!.win).toEqual({ count: 2500, seq: 1, beat: 1 });
  expect(panel.room.localPet.win).toEqual({ count: 30000, seq: 1, beat: 1 });
  desk.room.localPet.win = null;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.localPet.win).toBeNull();
});

it("mirrors the host, public flag and public list, and runs host actions in the desk", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const setPublic = vi.spyOn(desk.room, "setRoomPublic").mockImplementation(() => {
    desk.room.roomInfo.value = { host: "me", public: true };
  });
  const kick = vi.spyOn(desk.room, "kickMember").mockImplementation(() => {});
  const list = [{ room: "pub", host: { nick: "房主", character: "贝拉" }, members: 20, max: 20 }];
  const load = vi.spyOn(desk.room, "loadPublicRooms").mockImplementation(async () => { desk.room.publicRooms.value = list; });
  desk.room.roomInfo.value = { host: "me", public: false };
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.roomInfo.value).toEqual({ host: "me", public: false });
  panel.room.setRoomPublic(true);
  panel.room.kickMember("friend");
  await panel.room.loadPublicRooms();
  await vi.advanceTimersByTimeAsync(50);
  expect(setPublic).toHaveBeenCalledWith(true);
  expect(kick).toHaveBeenCalledWith("friend");
  expect(load).toHaveBeenCalledTimes(1);
  expect(panel.room.roomInfo.value).toEqual({ host: "me", public: true });
  expect(panel.room.publicRooms.value).toEqual(list);
  desk.room.roomInfo.value = null;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.roomInfo.value).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});

it("mirrors the duel into the panel and runs invites in the desk", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  const invite = vi.spyOn(desk.room, "inviteDuel").mockImplementation(() => {});
  panel.room.inviteDuel("friend", 1500);
  await vi.advanceTimersByTimeAsync(50);
  expect(invite).toHaveBeenCalledWith("friend", 1500);
  desk.room.members.set("friend", { id: "friend", nick: "朋友", character: "乃琳", taps: 0, pulse: 0, emote: null,
    combo: null, win: null, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
  desk.room.duel.value = { id: "d1", other: { id: "friend", nick: "朋友", character: "乃琳" }, sent: true, bet: 1500,
    prize: 2500, phase: "invite", answered: false, round: 0, sec: 15, until: Date.now() + 15000, hand: null, shown: null,
    won: false, reason: "" };
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.duel.value).toMatchObject({ id: "d1", phase: "invite" });
  expect(panel.room.duelBusy.value).toBe(true);
  desk.room.duel.value = null;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.duel.value).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});
