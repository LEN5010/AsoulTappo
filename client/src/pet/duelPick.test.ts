import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WsLike } from "../net/RoomClient";
import { DRAG_PX, dragged, isTap } from "./drag";

describe("click or drag on a pet", () => {
  it("is a drag once the pointer travels the threshold, and a click only when released without that", () => {
    expect(DRAG_PX).toBe(4);
    expect(dragged(0, 0)).toBe(false);
    expect(dragged(2, 3)).toBe(false);
    expect(dragged(3, 3)).toBe(true);
    expect(dragged(-4, 0)).toBe(true);
    expect(isTap(false, "pointerup")).toBe(true);
    expect(isTap(true, "pointerup")).toBe(false);
    expect(isTap(false, "pointercancel")).toBe(false);
    expect(isTap(false, "lostpointercapture")).toBe(false);
  });
});

class Socket implements WsLike {
  static all: Socket[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: WsLike["onopen"] = null;
  onmessage: WsLike["onmessage"] = null;
  onclose: WsLike["onclose"] = null;
  onerror: WsLike["onerror"] = null;
  constructor(public url: string) { Socket.all.push(this); }
  send(data: string) { this.sent.push(JSON.parse(data)); }
  open() { this.readyState = 1; this.onopen?.({}); }
  close() { this.readyState = 3; this.onclose?.({}); }
  recv(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}

const ME = { id: "me", uid: "u-me", nick: "me", character: "嘉然", taps: 0 };
const FRIEND = { id: "friend", uid: "u-friend", nick: "朋友", character: "乃琳", taps: 0 };
const GUEST = { id: "guest", uid: null, nick: "游客", character: "贝拉", taps: 0 };

describe("the bets over a partner's pet", () => {
  let leave: (() => void) | undefined;
  beforeEach(() => {
    vi.resetModules(); vi.useFakeTimers(); Socket.all = [];
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
    vi.stubGlobal("WebSocket", Socket);
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })));
  });
  afterEach(() => { leave?.(); vi.useRealTimers(); vi.unstubAllGlobals(); });

  async function setup() {
    const room = await import("../stores/room");
    const player = await import("../stores/player");
    const pick = await import("./duelPick");
    leave = room.leaveRoom;
    player.status.value = {
      player: "p", shards: 20000, income: { multiplier: 1, perMinute: 0 },
      resonance: { pity: { legendary: 0, skin: 0 }, hardPity: { legendary: 400, skin: 200 }, total: 0 },
      totals: { taps: 10000, activeMinutes: 0, owned: 0, items: 0 }, duel: { net: 0 },
    };
    room.joinRoom("r");
    const socket = Socket.all[0];
    socket.open();
    socket.recv({ type: "joined", room: "r", you: "me", members: [ME, FRIEND, GUEST] });
    return { room, player, pick, socket };
  }

  it("opens only for a member a duel looks possible with, one at a time", async () => {
    const { room, pick } = await setup();
    expect(pick.openPick(room.members.get("guest")!)).toBe(false); // no save
    expect(pick.openPick(room.members.get("me")!)).toBe(false);
    expect(pick.picking.value).toBeNull();
    expect(pick.openPick(room.members.get("friend")!)).toBe(true);
    expect(pick.picking.value).toBe("friend");
  });

  it("shows one key first, and the bets only once that key is pressed", async () => {
    const { room, pick } = await setup();
    pick.showStakes(); // nothing is open
    expect(pick.staking.value).toBe(false);
    pick.openPick(room.members.get("friend")!);
    expect(pick.staking.value).toBe(false);
    expect(pick.pickSize()).toEqual({ w: pick.ASK_WIDTH, h: pick.ASK_HEIGHT });
    pick.showStakes();
    expect(pick.staking.value).toBe(true);
    expect(pick.pickSize()).toEqual({ w: pick.PICK_WIDTH, h: pick.PICK_HEIGHT });
    // a click on the pet again starts over at the key
    pick.openPick(room.members.get("friend")!);
    expect(pick.staking.value).toBe(false);
    pick.showStakes();
    pick.closePick();
    expect(pick.staking.value).toBe(false);
  });

  it("sends the invite at the bet pressed and closes", async () => {
    const { room, pick, socket } = await setup();
    pick.openPick(room.members.get("friend")!);
    pick.showStakes();
    pick.pickStake(1500);
    expect(pick.picking.value).toBeNull();
    expect(pick.staking.value).toBe(false);
    expect(socket.sent.at(-1)).toEqual({ type: "duel_invite", id: "friend", bet: 1500 });
  });

  it("pressing the key restarts the six seconds", async () => {
    const { room, pick } = await setup();
    pick.openPick(room.members.get("friend")!);
    await vi.advanceTimersByTimeAsync(5000);
    pick.showStakes();
    await vi.advanceTimersByTimeAsync(5000);
    expect(pick.picking.value).toBe("friend");
    await vi.advanceTimersByTimeAsync(1000);
    expect(pick.picking.value).toBeNull();
  });

  it("closes after six seconds without the pointer on it", async () => {
    const { room, pick } = await setup();
    pick.openPick(room.members.get("friend")!);
    await vi.advanceTimersByTimeAsync(5000);
    pick.keepPick(); // the pointer moved over it
    await vi.advanceTimersByTimeAsync(5000);
    expect(pick.picking.value).toBe("friend");
    await vi.advanceTimersByTimeAsync(1000);
    expect(pick.picking.value).toBeNull();
  });

  it("closes when the partner leaves or a duel starts", async () => {
    const { room, pick, socket } = await setup();
    pick.openPick(room.members.get("friend")!);
    socket.recv({ type: "member_left", id: "friend" });
    expect(pick.picking.value).toBeNull();
    socket.recv({ type: "member_joined", member: FRIEND });
    pick.openPick(room.members.get("friend")!);
    socket.recv({ type: "duel_invite", duel: "d", from: "guest", to: "me", bet: 150, prize: 250, sec: 15 });
    expect(pick.picking.value).toBeNull();
  });

  it("tells a press on the bubble from a press elsewhere", async () => {
    const { pick } = await setup();
    const inside = { closest: (sel: string) => (sel === "[data-duel-pick]" ? {} : null) };
    const outside = { closest: () => null };
    expect(pick.insidePick(inside as unknown as EventTarget)).toBe(true);
    expect(pick.insidePick(outside as unknown as EventTarget)).toBe(false);
    expect(pick.insidePick(null)).toBe(false);
  });

  it("keeps the bubble on screen: shifted from the edges, under the pet near the top", async () => {
    const { pick } = await setup();
    const screen = { w: 1000, h: 700 };
    const pet = { w: 240, h: 170 };
    const bubble = { w: 204, h: 62 };
    expect(pick.bubblePlacement({ x: 400, y: 300 }, pet, bubble, screen)).toEqual({ shift: 0, below: false });
    // centered it would start at 8 - 18: moved right by 18
    expect(pick.bubblePlacement({ x: -10, y: 300 }, pet, bubble, screen)).toEqual({ shift: 8 - (-10 + 120 - 102), below: false });
    const right = pick.bubblePlacement({ x: 900, y: 300 }, pet, bubble, screen);
    expect(900 + 120 - 102 + right.shift + 204).toBe(1000 - 8);
    expect(pick.bubblePlacement({ x: 400, y: 60 }, pet, bubble, screen).below).toBe(true);
    expect(pick.bubblePlacement({ x: 400, y: 8 + 62 + 15 }, pet, bubble, screen).below).toBe(false);
  });
});


describe("poking and the profile key over a partner's pet", () => {
  let leave: (() => void) | undefined;
  beforeEach(() => {
    vi.resetModules(); vi.useFakeTimers(); Socket.all = [];
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
    vi.stubGlobal("WebSocket", Socket);
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })));
  });
  afterEach(() => { leave?.(); vi.useRealTimers(); vi.unstubAllGlobals(); });

  async function setup(features?: string[]) {
    const room = await import("../stores/room");
    const pick = await import("./duelPick");
    const ui = await import("../stores/ui");
    leave = room.leaveRoom;
    room.joinRoom("r");
    const socket = Socket.all[0];
    socket.open();
    socket.recv({ type: "joined", room: "r", you: "me", features,
      members: [ME, FRIEND, GUEST] });
    return { room, pick, ui: ui.ui, socket };
  }

  it("keeps the cheer bar and shows a finished round's shards over the paid pets", async () => {
    const { room, socket } = await setup(["cheer"]);
    expect(room.cheerOn.value).toBe(true);
    socket.recv({ type: "cheer", target: 600, minShare: 50, total: 300, shares: { me: 200, friend: 100 }, count: 2, reward: 20, rounds: 0 });
    expect(room.cheer.value).toMatchObject({ total: 300, shares: { me: 200, friend: 100 } });
    socket.recv({ type: "cheer_done", round: 1, rewards: { me: 30, friend: 30, guest: 0 } });
    expect(room.cheerDone.value).toEqual({ round: 1, got: 30 });
    expect(room.localPet.win).not.toBeNull();
    expect(room.members.get("friend")!.win).not.toBeNull();
    expect(room.members.get("guest")!.win).toBeNull();
    socket.close();
    expect(room.cheer.value).toBeNull();
    expect(room.cheerOn.value).toBe(false);
  });

  it("offers nothing on a server without pokes to a member a duel is not possible with", async () => {
    const { room, pick } = await setup(undefined);
    expect(pick.openPick(room.members.get("guest")!)).toBe(false);
  });

  it("pokes anyone else in the room, once per cooldown", async () => {
    const { room, pick, socket } = await setup(["poke"]);
    expect(pick.openPick(room.members.get("me")!)).toBe(false);
    expect(pick.openPick(room.members.get("guest")!)).toBe(true);
    expect(pick.pickKeys.value).toEqual({ poke: true, duel: false, profile: false });
    expect(pick.pickSize().w).toBe(pick.ASK_WIDTH);
    pick.pickPoke();
    expect(pick.picking.value).toBeNull();
    expect(socket.sent.at(-1)).toEqual({ type: "poke", id: "guest" });
    // Within the cooldown the server would refuse it, so nothing goes out.
    vi.advanceTimersByTime(room.POKE_MS - 1);
    expect(room.poke("friend")).toBe(false);
    vi.advanceTimersByTime(1);
    expect(room.poke("friend")).toBe(true);
    vi.advanceTimersByTime(room.POKE_MS);
    expect(room.poke("guest")).toBe(false); // the same member waits longer
    vi.advanceTimersByTime(room.POKE_SAME_MS);
    expect(room.poke("guest")).toBe(true);
  });

  it("sends a poke pressed inside the cooldown once it ends, and a refusal after all stays quiet", async () => {
    const { room, socket } = await setup(["poke"]);
    room.pokeSoon("guest");
    expect(socket.sent.filter((m) => m.type === "poke")).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    room.pokeSoon("guest"); // poking back right away
    expect(socket.sent.filter((m) => m.type === "poke")).toHaveLength(1);
    vi.advanceTimersByTime(room.POKE_SAME_MS - 1000 - 1);
    expect(socket.sent.filter((m) => m.type === "poke")).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(socket.sent.filter((m) => m.type === "poke")).toHaveLength(2);
    socket.recv({ type: "error", code: "poke_cooldown", message: "" });
    expect(room.lastError.value).toBe("");
  });

  it("shows who poked the own pet, unless quiet, and bounces a partner's pet poked by someone else", async () => {
    const { room, socket } = await setup(["poke"]);
    socket.recv({ type: "poke", from: "friend", to: "guest" });
    expect(room.members.get("guest")!.pulse).toBe(1);
    expect(room.poked.value).toBeNull();
    socket.recv({ type: "poke", from: "friend", to: "me", quiet: true });
    expect(room.localPet.pulse).toBe(1);
    expect(room.poked.value).toBeNull();
    socket.recv({ type: "poke", from: "friend", to: "me" });
    expect(room.localPet.pulse).toBe(2);
    expect(room.poked.value).toEqual({ id: "friend", nick: "朋友" });
    vi.advanceTimersByTime(room.POKED_MS);
    expect(room.poked.value).toBeNull();
  });

  it("forgets pokes and the bubble when the connection drops", async () => {
    const { room, socket } = await setup(["poke"]);
    socket.recv({ type: "poke", from: "friend", to: "me" });
    expect(room.poke("friend")).toBe(true);
    socket.close();
    expect(room.pokeOn.value).toBe(false);
    expect(room.poked.value).toBeNull();
  });

  it("opens the panel on a partner's profile over the room page", async () => {
    const { room, pick, ui } = await setup(["poke", "profile"]);
    expect(pick.openPick(room.members.get("me")!)).toBe(false);
    expect(pick.openPick(room.members.get("guest")!)).toBe(true);
    expect(pick.pickKeys.value).toEqual({ poke: true, duel: false, profile: true });
    pick.pickProfile();
    expect(ui.page).toBe("room");
    expect(ui.craftTarget).toBe("profile:guest");
    expect(pick.picking.value).toBeNull();
  });

  it("asks the server for profiles one at a time, and gives up on no answer or a dropped connection", async () => {
    const { room, socket } = await setup(["profile"]);
    const progress = { cards: [1, 85], emotes: [20, 495], skins: [0, 9] };
    const friend = room.loadProfile("friend");
    const again = room.loadProfile("friend");
    const guest = room.loadProfile("guest");
    await vi.advanceTimersByTimeAsync(0);
    // one request answers both waits for the same member; the next waits for the server's spacing
    expect(socket.sent.filter((m) => m.type === "profile")).toEqual([{ type: "profile", id: "friend" }]);
    socket.recv({ type: "profile", id: "friend", showcase: ["c1"], progress });
    await expect(friend).resolves.toEqual({ showcase: ["c1"], progress });
    await expect(again).resolves.toEqual({ showcase: ["c1"], progress });
    await vi.advanceTimersByTimeAsync(room.PROFILE_GAP_MS);
    expect(socket.sent.at(-1)).toEqual({ type: "profile", id: "guest" });
    await vi.advanceTimersByTimeAsync(room.PROFILE_TIMEOUT_MS);
    await expect(guest).resolves.toBeNull();
    expect(await room.loadProfile("me")).toBeNull(); // the own profile is read locally
    const dropped = room.loadProfile("friend");
    await vi.advanceTimersByTimeAsync(room.PROFILE_GAP_MS);
    socket.close();
    await expect(dropped).resolves.toBeNull();
    expect(room.profileOn.value).toBe(false);
  });
});
