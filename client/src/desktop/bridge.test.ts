import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Board } from "../net/api";
import type { MemberProfile } from "../net/protocol";
import { exampleEconomy } from "../test/economy";

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
  // A connection that stays on its way: a table of the queue's brings the desk's up.
  vi.stubGlobal("WebSocket", class { readyState = 0; send() {} close() {} });
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

/** The desk (false), the panel (true) or the dou dizhu table's window ("ddz"). */
async function context(panel: boolean | "ddz") {
  vi.resetModules();
  vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: panel === "ddz" ? "?window=ddz" : panel ? "?window=panel" : "" } });
  const uiStore = await import("../stores/ui");
  if (panel === true) uiStore.ui.panelOpen = true;
  // The table's window says it is on screen (DdzApp.vue) once it has drawn.
  if (panel === "ddz") uiStore.ui.ddzSeen = true;
  const bridge = await import("./bridge");
  stops.push(await bridge.initDesktop());
  return {
    settings: (await import("../stores/settings")).settings,
    player: await import("../stores/player"),
    room: await import("../stores/room"),
    ddz: await import("../stores/ddz"),
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
  panel.settings.showcase.push("card");
  panel.settings.onBoard = false;
  expect(desk.settings.showcase).toEqual(["card"]);
  expect(desk.settings.onBoard).toBe(false);
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
  expect(desk.player.resonate).toHaveBeenCalledWith(1, undefined);
  expect(panel.player.collection.owned["card:test"]).toBe(1);
});

it("refreshes a panel's expired economy in the desk and publishes the replacement", async () => {
  const desk = await context(false);
  const deskEconomy = await import("../stores/economy");
  const panel = await context(true);
  const panelEconomy = await import("../stores/economy");
  const { agree } = await import("../legal/consent");
  agree();
  let answer!: (value: Response) => void;
  const pending = new Promise<Response>((resolve) => { answer = resolve; });
  const fetchEconomy = vi.fn(() => pending);
  vi.stubGlobal("fetch", fetchEconomy);
  const refresh = Promise.all([desk.player.loadEconomy(), panel.player.loadEconomy()]);
  await vi.advanceTimersByTimeAsync(0);
  answer(new Response(JSON.stringify(exampleEconomy)));
  await refresh;
  expect(fetchEconomy).toHaveBeenCalledTimes(1);
  expect(deskEconomy.economy.value?.resonance.cost).toBe(exampleEconomy.resonance.cost);
  expect(panelEconomy.economy.value?.resonance.cost).toBe(exampleEconomy.resonance.cost);
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

it("relays park requests from the panel to the desk, with the park state and the server's error code", async () => {
  const desk = await context(false);
  const deskPark = await import("../stores/park");
  const panel = await context(true);
  const panelPark = await import("../stores/park");
  const state = { coins: 4, unlocked: true, gift: false, stamps: 0, stampsTotal: 0, badge: 0,
    today: { spent: 500, won: 0 }, jackpot: 30000 };
  const request = vi.spyOn(deskPark, "parkRequest").mockImplementation(async (_method, path) => {
    if (path === "/api/park/coins") return { ok: false, error: { status: 409, code: "no_shards", message: "碎片不足", detail: {} } };
    deskPark.park.value = state;
    return { ok: true, data: state };
  });
  expect(await panelPark.loadPark()).toEqual(state);
  expect(request).toHaveBeenCalledWith("GET", "/api/park", null);
  expect(panelPark.park.value).toEqual(state);
  expect(await panelPark.buyCoins(1)).toBe(false);
  expect(request).toHaveBeenLastCalledWith("POST", "/api/park/coins", { count: 1 });
  expect(panelPark.parkError.value).toMatchObject({ status: 409, code: "no_shards" });
  expect(desk.player.status.value).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
  void panel;
});

it("sends a feedback from the panel through the desk, which reads the log itself", async () => {
  const desk = await context(false);
  const { TERMS_VERSION } = await import("../legal");
  const { APP_VERSION } = await import("../version");
  desk.settings.termsAgreed = TERMS_VERSION;
  desk.settings.statementSeen = APP_VERSION;
  await context(true);
  const { invoke } = await import("@tauri-apps/api/core");
  vi.mocked(invoke).mockImplementation(async (cmd: string) => (cmd === "log_tail" ? "the log\n" : undefined));
  const posted: unknown[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (String(url).endsWith("/api/feedback")) posted.push(JSON.parse(init!.body as string));
    return { ok: true, status: 200, json: async () => ({ id: 1, left: 4 }) } as Response;
  });
  const feedback = await import("../stores/feedback");
  expect(await feedback.sendFeedback({ text: "抖", contact: "", log: true })).toEqual({ ok: true, left: 4 });
  expect(posted).toEqual([expect.objectContaining({ text: "抖", log: "the log\n" })]);
  expect(await feedback.sendFeedback({ text: "抖", contact: "", log: false })).toEqual({ ok: true, left: 4 });
  expect(posted[1]).toMatchObject({ log: "" });
  // The panel names the draft; the desk sends that request id as it is.
  const going = feedback.submitFeedback({ text: "抖", contact: "", log: false });
  const id = feedback.feedbackSending.value?.draft.requestId;
  expect(await going).toEqual({ ok: true, left: 4 });
  expect(id).toMatch(/^[0-9a-f]{32}$/);
  expect(posted[2]).toMatchObject({ text: "抖", requestId: id });
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
      pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { ...pose } });
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
    pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { ...resting } });
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
    pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
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
    pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
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

it("runs profile and board requests in the desk and hands the panel their answers", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const profile: MemberProfile = { showcase: ["card"], progress: { cards: [1, 85], emotes: [0, 495], skins: [0, 9] } };
  const board: Board = { total: 85, points: {}, cards: [], me: { rank: null, cards: 1, big: 0, skins: 0, score: 2, off: "account" } };
  const room = vi.spyOn(desk.room, "loadProfile").mockResolvedValue(profile);
  const boards = vi.spyOn(desk.player, "loadBoard").mockResolvedValue(board);
  const row = vi.spyOn(desk.player, "loadBoardProfile").mockResolvedValue(null);
  expect(await panel.room.loadProfile("m2")).toEqual(profile);
  expect(room).toHaveBeenCalledWith("m2");
  expect(await panel.player.loadBoard()).toEqual(board);
  expect(boards).toHaveBeenCalledTimes(1);
  expect(await panel.player.loadBoardProfile("abc")).toBeNull();
  expect(row).toHaveBeenCalledWith("abc");
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
    combo: null, win: null, sip: 0, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
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

it("mirrors the dou dizhu table and the room's games into the panel and runs the panel's moves in the desk", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  desk.room.youId.value = "me";
  desk.ddz.onDdzMessage({ type: "ddz_invite", table: "t1", from: "host", ids: ["host", "me", "third"], base: 100, deposit: 4800, sec: 15 });
  desk.ddz.onDdzMessage({ type: "ddz_live", table: "t2", ids: ["x", "y", "z"], on: true });
  desk.ddz.onDdzMessage({ type: "ddz_live_state", table: "t2", landlord: 1, seats: [{ left: 17 }, { left: 15 }, { left: 17 }], mult: 2, watching: 0 });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.ddz.ddz.value).toMatchObject({ id: "t1", phase: "invite", you: 1, sent: false, base: 100, deposit: 4800 });
  expect(panel.ddz.ddzBusy.value).toBe(true);
  expect([...panel.ddz.ddzPlaying.value]).toEqual(["x", "y", "z"]);
  expect(panel.ddz.ddzLiveState.value).toEqual({ t2: { landlord: 1, left: [17, 15, 17], mult: 2, watching: 0 } });
  const request = vi.spyOn(desk.ddz, "ddzRequest").mockImplementation(() => {});
  panel.ddz.answerDdz(true);
  panel.ddz.playDdz([0, 1]);
  await vi.advanceTimersByTimeAsync(50);
  // The answer names the table the panel showed, so the desk cannot apply it to another one.
  expect(request.mock.calls).toEqual([["answer", true, "t1"], ["play", [0, 1]]]);
  desk.ddz.ddz.value = null;
  desk.ddz.onDdzMessage({ type: "ddz_live", table: "t2", ids: ["x", "y", "z"], on: false });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.ddz.ddz.value).toBeNull();
  expect(panel.ddz.ddzPlaying.value.size).toBe(0);
  expect(panel.ddz.ddzLiveState.value).toEqual({});
  expect(fetch).not.toHaveBeenCalled();
});

it("mirrors the dou dizhu queue into the panel and runs the panel's queueing in the desk", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  desk.room.youId.value = "me";
  desk.room.ddzMatchOn.value = true;
  desk.ddz.onDdzMessage({ type: "ddz_queue", base: 50, waited: 4 });
  desk.ddz.onDdzMessage({ type: "ddz_waiting", counts: [[50, 2]] });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.ddzMatchOn.value).toBe(true);
  expect(panel.ddz.ddzQueue.value).toEqual(desk.ddz.ddzQueue.value);
  expect(panel.ddz.ddzQueue.value!.base).toBe(50);
  expect(panel.ddz.ddzOthersWaiting(50)).toBe(1);
  const request = vi.spyOn(desk.ddz, "ddzRequest").mockImplementation(() => {});
  panel.ddz.unqueueDdz();
  panel.ddz.queueDdz(250);
  await vi.advanceTimersByTimeAsync(50);
  expect(request.mock.calls).toEqual([["unqueue"], ["queue", 250]]);
  desk.ddz.onDdzMessage({ type: "ddz_queue", base: null });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.ddz.ddzQueue.value).toBeNull();
});

it("mirrors the dou dizhu connection and the table's emotes, and runs the table window's emotes and lobby reads in the desk", async () => {
  const desk = await context(false);
  const table = await context("ddz");
  await vi.advanceTimersByTimeAsync(50);
  desk.room.youId.value = "me";
  desk.ddz.ddzLink.value = "reconnecting";
  const seats = ["a", "me", "b"].map((id) => ({ id, nick: id, character: "乃琳", auto: false, away: false }));
  desk.ddz.onDdzMessage({
    type: "ddz_deal", table: "t", seats, you: 1, hand: [0, 1, 52], base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0,
  });
  desk.ddz.onDdzMessage({ type: "ddz_emote", table: "t", seat: 2, emote: "thumbup" });
  await vi.advanceTimersByTimeAsync(50);
  expect(table.ddz.ddzLink.value).toBe("reconnecting");
  expect(table.ddz.ddzEmotes.value.map((f) => f?.key ?? null)).toEqual([null, null, "thumbup"]);
  const request = vi.spyOn(desk.ddz, "ddzRequest").mockImplementation(() => {});
  table.ddz.emoteDdz("thumbup");
  await vi.advanceTimersByTimeAsync(50);
  expect(request.mock.calls).toEqual([["emote", "thumbup"]]);
  // The lobby is read by the desk, which holds the save's credentials; the window gets the answer.
  const lobby = {
    tiers: [{ base: 50, deposit: 2400, afford: true, waiting: 2 }], net: 0, cap: 50000, left: 50000, taps: 10000,
    minTaps: 10000, account: true, seated: false,
  };
  const read = vi.spyOn(desk.player, "loadDdzLobby").mockResolvedValue(lobby);
  expect(await table.player.loadDdzLobby()).toEqual(lobby);
  read.mockResolvedValue("off");
  expect(await table.player.loadDdzLobby()).toBe("off");
  expect(read).toHaveBeenCalledTimes(2);
  desk.ddz.ddzLinkOff.value = true;
  await vi.advanceTimersByTimeAsync(50);
  expect(table.ddz.ddzLinkOff.value).toBe(true);
});

it("mirrors the table into its own window beside the panel, runs its moves in the desk, and stops when it closes", async () => {
  const desk = await context(false);
  const { invoke } = await import("@tauri-apps/api/core");
  const panel = await context(true);
  panel.ui.ui.page = "room";
  desk.counter.total = 7;
  desk.room.youId.value = "me";
  const seats = ["a", "me", "b"].map((id) => ({ id, nick: id, character: "乃琳", auto: false, away: false }));
  desk.ddz.onDdzMessage({
    type: "ddz_deal", table: "t", seats, you: 1, hand: [0, 1, 52], base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0,
  });
  // The desk opens the table's window with the deal; the panel is not asked to show anything.
  expect(invoke).toHaveBeenCalledWith("open_ddz", { auto: true });
  expect(invoke).not.toHaveBeenCalledWith("open_panel", expect.anything());
  const table = await context("ddz");
  await vi.advanceTimersByTimeAsync(50);
  // It gets the whole state when it comes up, though the panel was up already.
  expect(table.counter.total).toBe(7);
  expect(table.ddz.ddz.value).toMatchObject({ id: "t", phase: "bid", you: 1, hand: [52, 0, 1] });
  expect(table.ddz.ddzAtTable.value).toBe(true);
  expect(desk.ui.ui.ddzSeen).toBe(true);
  expect(desk.ddz.ddzBubble.value).toBeNull();
  desk.ddz.onDdzMessage({ type: "ddz_bid", table: "t", seat: 0, bid: 1, turn: 1, sec: 15 });
  await vi.advanceTimersByTimeAsync(50);
  expect(table.ddz.ddz.value!.seats[0]!.bid).toBe(1);
  expect(panel.ddz.ddz.value!.seats[0]!.bid).toBe(1);
  const request = vi.spyOn(desk.ddz, "ddzRequest").mockImplementation(() => {});
  table.ddz.bidDdz(3);
  table.ddz.autoDdz(true);
  await vi.advanceTimersByTimeAsync(50);
  expect(request.mock.calls).toEqual([["bid", 3], ["auto", true]]);
  // Minimized, the window still follows the game, and the pet's bubble says whose move it is.
  table.ui.ui.ddzSeen = false;
  await vi.advanceTimersByTimeAsync(50);
  expect(desk.ddz.ddzBubble.value).toBe("turn");
  table.ui.ui.ddzSeen = true;
  await vi.advanceTimersByTimeAsync(50);
  // Closed: nothing more goes to it, and the game goes on.
  const { emitTo } = await import("@tauri-apps/api/event");
  await emitTo("main", "ddz:closed", null);
  expect(desk.ui.ui.ddzSeen).toBe(false);
  expect(desk.ddz.ddzBubble.value).toBe("turn");
  desk.ddz.onDdzMessage({ type: "ddz_bid", table: "t", seat: 1, bid: 2, turn: 2, sec: 15 });
  await vi.advanceTimersByTimeAsync(50);
  expect(table.ddz.ddz.value!.seats[1]!.bid).toBeNull();
  expect(panel.ddz.ddz.value!.seats[1]!.bid).toBe(2);
});

it("mirrors the game watched and its watchers, runs the windows' watching in the desk, and stops when the table's window closes", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  const table = await context("ddz");
  await vi.advanceTimersByTimeAsync(50);
  desk.room.ddzWatchOn.value = true;
  const seats = ["a", "x", "b"].map((id) => ({ id, nick: id, character: "乃琳", left: 17, bid: null, auto: false, away: false, again: false }));
  desk.ddz.ddzWatch.value = {
    id: "w", via: "room", phase: "play", you: 2, seats, hand: [52, 1], shown: true, switching: false, ended: "", log: [],
    trick: [null, null, null], landlord: 2, bottom: [], turn: 0, sec: 30, until: Date.now() + 30000, result: null,
  } as unknown as typeof desk.ddz.ddzWatch.value;
  desk.ddz.onDdzMessage({ type: "ddz_watchers", table: "w", faces: [{ nick: "我", character: "嘉然", seat: 2 }] });
  await vi.advanceTimersByTimeAsync(50);
  expect(desk.room.ddzWatchOn.value).toBe(true);
  expect(panel.room.ddzWatchOn.value).toBe(true);
  for (const w of [panel, table]) {
    expect(w.ddz.ddzWatch.value).toMatchObject({ id: "w", you: 2, hand: [52, 1], shown: true });
    expect(w.ddz.ddzWatchers.value).toEqual({ w: [{ nick: "我", character: "嘉然", seat: 2 }] });
    expect(w.ddz.ddzScreen.value).toBe("watch");
    // Watching holds nothing of the save's.
    expect(w.ddz.ddzBusy.value).toBe(false);
  }
  const request = vi.spyOn(desk.ddz, "ddzRequest").mockImplementation(() => {});
  panel.ddz.watchDdz("w2", 1);
  table.ddz.viewDdz(0);
  table.ddz.unwatchDdz();
  await vi.advanceTimersByTimeAsync(50);
  expect(request.mock.calls).toEqual([["watch", "w2", 1], ["view", 0], ["unwatch"]]);
  request.mockRestore();
  // The watcher closed the table's window: watching stops in the desk, and in the windows that mirror it.
  const { emitTo } = await import("@tauri-apps/api/event");
  await emitTo("main", "ddz:closed", null);
  expect(desk.ddz.ddzWatch.value).toBeNull();
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.ddz.ddzWatch.value).toBeNull();
  expect(panel.ddz.ddzWatchers.value).toEqual({});
});

it("runs the table window's leave in the desk, in a game and on the result, and not for a table gone", async () => {
  const desk = await context(false);
  desk.room.youId.value = "me";
  const seats = ["a", "me", "b"].map((id) => ({ id, nick: id, character: "乃琳", auto: false, away: false }));
  const deal = (table: string) => desk.ddz.onDdzMessage({
    type: "ddz_deal", table, seats, you: 1, hand: [0, 1, 52], base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0,
  });
  deal("t");
  const table = await context("ddz");
  await vi.advanceTimersByTimeAsync(50);
  // The window names its table and no phase: the phase left out reaches the desk as null over the bridge.
  table.ddz.leaveDdz("old");
  await vi.advanceTimersByTimeAsync(50);
  expect(desk.ddz.ddz.value).toMatchObject({ id: "t", phase: "bid" });
  table.ddz.leaveDdz("t");
  await vi.advanceTimersByTimeAsync(50);
  expect(desk.ddz.ddz.value).toBeNull();
  deal("t2");
  desk.ddz.ddz.value!.phase = "result";
  await vi.advanceTimersByTimeAsync(50);
  expect(table.ddz.ddz.value).toMatchObject({ id: "t2", phase: "result" });
  table.ddz.leaveDdz("t2");
  await vi.advanceTimersByTimeAsync(50);
  expect(desk.ddz.ddz.value).toBeNull();
});

it("keeps a pet's pose that reaches the panel before the member and applies it once the member arrives", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  const { emitTo } = await import("@tauri-apps/api/event");
  const pose = { dx: 3, dy: 2, keyDown: false, left: false, right: true };
  // Two updates for a member the panel has not heard of yet (its state goes over more slowly): they merge.
  await emitTo("panel", "desktop:motion", { members: [{ id: "late", motion: { ...pose, dx: 1 } }], local: { emote: null, win: null } });
  await emitTo("panel", "desktop:motion", { members: [{ id: "late", motion: pose }], local: { emote: null, win: null } });
  expect(panel.room.members.has("late")).toBe(false);
  desk.room.members.set("late", { id: "late", nick: "迟到", character: "贝拉", taps: 0,
    pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
  await vi.advanceTimersByTimeAsync(50);
  // The pose waits for the member; its taps come from the desk, which holds the current count.
  const late = panel.room.members.get("late")!;
  expect(late.motion).toEqual(pose);
  expect(late.taps).toBe(0);
  const drawn: unknown[] = [];
  panel.motion.subscribe("late", (shown) => drawn.push({ ...shown }));
  expect(drawn[0]).toEqual(pose);
});

it("forgets a member's pose in the panel once the member leaves", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  const pose = { dx: 6, dy: 0, keyDown: true, left: false, right: false };
  desk.room.members.set("gone", { id: "gone", nick: "走了", character: "嘉然", taps: 0,
    pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { ...pose } });
  await vi.advanceTimersByTimeAsync(50);
  const stop = panel.motion.subscribe("gone", () => {});
  await vi.advanceTimersByTimeAsync(50);
  stop();
  desk.room.members.delete("gone");
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.room.members.has("gone")).toBe(false);
  // A pet drawn for that id again starts from rest, not from the old pose.
  const drawn: unknown[] = [];
  panel.motion.subscribe("gone", (shown) => drawn.push({ ...shown }));
  expect(drawn[0]).toEqual({ dx: 0, dy: 0, keyDown: false, left: false, right: false });
});

it("asks the room for no poses while the panel window is off screen, and again once it is back", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const activity = await import("../stores/activity");
  panel.ui.ui.page = "room";
  desk.room.members.set("friend", { id: "friend", nick: "朋友", character: "乃琳", taps: 0,
    pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: { dx: 0, dy: 0, keyDown: false, left: false, right: false } });
  await vi.advanceTimersByTimeAsync(50);
  const subscribed = vi.spyOn(desk.room, "setPanelMotionInterest");
  panel.motion.subscribe("friend", () => {});
  await vi.advanceTimersByTimeAsync(50);
  expect(subscribed).toHaveBeenLastCalledWith(["friend"]);
  activity.windowVisible.value = false;
  await vi.advanceTimersByTimeAsync(50);
  expect(subscribed).toHaveBeenLastCalledWith([]);
  activity.windowVisible.value = true;
  await vi.advanceTimersByTimeAsync(50);
  expect(subscribed).toHaveBeenLastCalledWith(["friend"]);
});

it("drops the panel's pose subscription when the desk bridge stops", async () => {
  const desk = await context(false);
  const subscribed = vi.spyOn(desk.room, "setPanelMotionInterest");
  stops.shift()!();
  expect(subscribed).toHaveBeenLastCalledWith([]);
});

it("shows the desk's todos in the panel and changes them in the desk", async () => {
  await context(false);
  const deskTodos = await import("../stores/todo");
  deskTodos.addTodo({ title: "交周报", at: null, allDay: false, repeat: "none" });
  await context(true);
  const panelTodos = await import("../stores/todo");
  expect(panelTodos.todos.value.map((t) => t.title)).toEqual(["交周报"]);
  panelTodos.addTodo({ title: "开会", at: null, allDay: false, repeat: "none" });
  await vi.advanceTimersByTimeAsync(50);
  expect(deskTodos.todos.value.map((t) => t.title)).toEqual(["交周报", "开会"]);
  expect(panelTodos.todos.value.map((t) => t.title)).toEqual(["交周报", "开会"]);
  panelTodos.finishTodo(deskTodos.todos.value[0].id);
  await vi.advanceTimersByTimeAsync(50);
  expect(deskTodos.todos.value[0].doneAt).not.toBeNull();
  expect(panelTodos.todos.value[0].doneAt).not.toBeNull();
});

/** The todos' own window of the app, on its light bridge (desktop/todoBridge.ts). */
async function todoWindow() {
  vi.resetModules();
  vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: "?window=todo" } });
  const bridge = await import("./todoBridge");
  stops.push(await bridge.initTodoWindow());
  return { settings: (await import("../stores/settings")).settings, todos: await import("../stores/todo") };
}

it("shows the desk's todos in the todos' window without any interest message, and changes them in the desk", async () => {
  await context(false);
  const deskTodos = await import("../stores/todo");
  deskTodos.addTodo({ title: "交周报", at: null, allDay: false, repeat: "none" });
  const win = await todoWindow();
  expect(win.todos.todos.value.map((t) => t.title)).toEqual(["交周报"]);
  win.todos.addTodo({ title: "开会", at: null, allDay: false, repeat: "none" });
  await vi.advanceTimersByTimeAsync(0);
  expect(deskTodos.todos.value.map((t) => t.title)).toEqual(["交周报", "开会"]);
  expect(win.todos.todos.value.map((t) => t.title)).toEqual(["交周报", "开会"]);
  const [first, second] = deskTodos.todos.value;
  win.todos.finishTodo(first.id);
  win.todos.editTitle(second.id, "开周会");
  win.todos.editWhen(second.id, { at: new Date(2026, 10, 17, 15).getTime(), allDay: true, repeat: "weekly" });
  await vi.advanceTimersByTimeAsync(0);
  expect(deskTodos.todos.value[0].doneAt).not.toBeNull();
  expect(deskTodos.todos.value[1]).toMatchObject({ title: "开周会", allDay: true, repeat: "weekly" });
  expect(win.todos.todos.value).toEqual(deskTodos.todos.value);
  win.todos.removeTodo(first.id);
  await vi.advanceTimersByTimeAsync(0);
  expect(win.todos.todos.value.map((t) => t.title)).toEqual(["开周会"]);
});

it("answers the window that asked: the todos' window and the panel side by side", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const win = await todoWindow();
  const board = { players: [] } as unknown as Board;
  vi.spyOn(desk.player, "loadBoard").mockResolvedValue(board);
  const { requestDesktop } = await import("./transport");
  const asked = requestDesktop("todo", "add", { title: "取快递", at: null, allDay: false, repeat: "none" });
  expect(await panel.player.loadBoard()).toEqual(board);
  await expect(asked).resolves.toBeUndefined();
  expect(win.todos.todos.value.map((t) => t.title)).toEqual(["取快递"]);
});

it("passes setting edits between the desk, the panel and the todos' window", async () => {
  const desk = await context(false);
  const panel = await context(true);
  const win = await todoWindow();
  win.settings.todoPinned = false;
  expect(desk.settings.todoPinned).toBe(false);
  expect(panel.settings.todoPinned).toBe(false);
  panel.settings.nick = "阿草";
  expect(win.settings.nick).toBe("阿草");
  desk.settings.todoSound = false;
  expect(win.settings.todoSound).toBe(false);
  expect(panel.settings.todoSound).toBe(false);
});

it("passes the panel's opening queue to the desk for the first-run guide", async () => {
  const desk = await context(false);
  const deskStore = await import("../stores/guide");
  const deskGuide = deskStore.guideLink;
  const panel = await context(true);
  const panelGuide = (await import("../stores/guide")).guideLink;
  await vi.advanceTimersByTimeAsync(0);
  expect(deskGuide.panelVisible).toBe(true);
  panelGuide.panelBusy = true;
  await vi.advanceTimersByTimeAsync(0);
  expect(deskGuide).toMatchObject({ panelVisible: true, panelBusy: true });
  // Hidden or minimized: what it opens with still counts until it is through, also when it changes while hidden.
  panel.ui.ui.panelOpen = false;
  await vi.advanceTimersByTimeAsync(0);
  expect(deskGuide).toMatchObject({ panelVisible: false, panelBusy: true });
  panelGuide.panelBusy = false;
  await vi.advanceTimersByTimeAsync(0);
  expect(deskGuide.panelBusy).toBe(false);
  panelGuide.panelBusy = true;
  await vi.advanceTimersByTimeAsync(0);
  expect(deskGuide.panelBusy).toBe(true);
  panel.ui.ui.panelOpen = true;
  await vi.advanceTimersByTimeAsync(0);
  expect(deskGuide).toMatchObject({ panelVisible: true, panelBusy: true });
  // Answered in one window, answered in both: the progress is replaced as a whole, so the patch carries it.
  deskStore.finishCard("panel");
  expect(desk.settings.guide.done).toEqual(["panel"]);
  expect(panel.settings.guide.done).toEqual(["panel"]);
});

it("keeps the guide's progress from both windows when their changes cross", async () => {
  const desk = await context(false);
  const deskStore = await import("../stores/guide");
  const panel = await context(true);
  const panelStore = await import("../stores/guide");
  desk.settings.guide = { v: 1, done: [] };
  expect(panel.settings.guide.v).toBe(1);
  // The bridge delivers each window's patch before the other's own edit has gone out: a replace would lose one.
  const { emitTo } = await import("@tauri-apps/api/event");
  const send = vi.mocked(emitTo);
  const deliver = async (target: string, event: string, payload: unknown) => {
    const copy = JSON.parse(JSON.stringify(payload));
    await Promise.all([...bus.listeners.get(`${target}:${event}`) ?? []].map((cb) => cb({ payload: copy })));
  };
  const held: [string, string, unknown][] = [];
  send.mockImplementation(async (target, event, payload) => { held.push([target as string, event, payload]); });
  deskStore.finishCard("tap");
  panelStore.finishCard("grip");
  panelStore.finishCard("draw");
  send.mockImplementation((target, event, payload) => deliver(target as string, event, payload));
  for (const [target, event, payload] of held) await deliver(target, event, payload);
  for (const s of [desk.settings, panel.settings]) {
    expect(s.guide.done.sort()).toEqual(["draw", "grip", "tap"]);
  }
});

it("mirrors open tables and a call into the panel and runs the panel's sitting and calling in the desk", async () => {
  const desk = await context(false);
  const panel = await context(true);
  panel.ui.ui.page = "room";
  await vi.advanceTimersByTimeAsync(50);
  desk.room.youId.value = "me";
  desk.room.members.set("a", { id: "a", uid: "u-a", nick: "贝", character: "贝拉", taps: 0, ddz: true, ddzMatch: true, pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: {} as never });
  const tables = [{ table: "o1", base: 50, seats: [{ id: "a", nick: "贝", character: "贝拉" }, null, null] }];
  desk.ddz.onDdzMessage({ type: "ddz_tables", tables });
  desk.ddz.onDdzMessage({ type: "ddz_call", table: "o1", from: "a", base: 50, deposit: 2400, sec: 15, seats: tables[0]!.seats });
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.ddz.ddzTables.value).toEqual(tables);
  expect(panel.ddz.ddzCall.value).toEqual(desk.ddz.ddzCall.value);
  expect(panel.room.members.get("a")!.ddzMatch).toBe(true);
  // Whether the server has the hall, as the desk's last lobby said.
  expect(panel.player.ddzHallOn.value).toBe(false);
  desk.player.ddzHallOn.value = true;
  await vi.advanceTimersByTimeAsync(50);
  expect(panel.player.ddzHallOn.value).toBe(true);
  const request = vi.spyOn(desk.ddz, "ddzRequest").mockImplementation(() => {});
  panel.ddz.openDdz(50);
  panel.ddz.sitDdz("o1", 2);
  panel.ddz.callDdz("a", "o1");
  panel.ddz.leaveDdz("o1", "open");
  panel.ddz.dismissDdzCall();
  panel.ddz.quickSitDdz(50);
  panel.ddz.sitDdzAt("h1");
  await vi.advanceTimersByTimeAsync(50);
  // The table the key was pressed for goes with the request, for the desk to check against its own.
  expect(request.mock.calls).toEqual([
    ["open", 50], ["sit", "o1", 2], ["call", "a", "o1"], ["leave", "o1", "open"], ["dismiss"], ["quickSit", 50], ["sitAt", "h1", null, null],
  ]);
});
