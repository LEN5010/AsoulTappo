import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TERMS_VERSION } from "../legal";
import type { ParkState, PlayerStatus } from "../net/api";

const response = (data: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => data }) as Response;

const state = (over: Partial<ParkState> = {}): ParkState => ({
  coins: 3, unlocked: true, bought: 2, buyLeft: 38, gift: false, stamps: 4, stampsTotal: 34, badge: 0,
  today: { spent: 1000, won: 0 }, jackpot: 30000, ...over,
});
const playerStatus = (over: Partial<PlayerStatus> = {}): PlayerStatus => ({
  player: "p1", shards: 5000, income: { multiplier: 1, perMinute: 0 },
  resonance: { pity: { legendary: 0, skin: 0 }, hardPity: { legendary: 90, skin: 200 }, total: 0 },
  totals: { taps: 20000, activeMinutes: 0, owned: 0, items: 0 },
  park: { coins: 3, news: [{ id: 1, ts: 1, kind: "jackpot", nick: "a", shards: 50000 }] }, ...over,
});

let saved: Map<string, string>;
beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  saved = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => saved.get(k) ?? null, setItem: (k: string, v: string) => saved.set(k, v), removeItem: (k: string) => saved.delete(k),
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function load() {
  const { settings } = await import("./settings");
  settings.serverUrl = "http://a";
  settings.termsAgreed = TERMS_VERSION;
  return { settings, player: await import("./player"), park: await import("./park") };
}

it("splits an answer into the player status and the park state", async () => {
  const { park } = await load();
  const prev = playerStatus();
  // A park request's answer: its `park` is the whole state, which the status keeps only as coins and the old news.
  const answer = { ...playerStatus({ shards: 4500 }), park: state({ coins: 4 }), gift: 1 };
  const split = park.splitParkResult(answer, prev);
  expect(split.park).toEqual(state({ coins: 4 }));
  expect(split.status?.shards).toBe(4500);
  expect(split.status?.park).toEqual({ coins: 4, news: prev.park!.news });
  // GET /api/park: the bare state.
  expect(park.splitParkResult(state(), prev)).toEqual({ status: null, park: state() });
  // A status of its own keeps its park; one without any keeps the previous.
  const own = playerStatus({ park: { coins: 9, news: [] } });
  expect(park.splitParkResult(own, prev)).toEqual({ status: own, park: null });
  const { park: _, ...bare } = playerStatus();
  expect(park.splitParkResult(bare, prev).status?.park).toEqual(prev.park);
  // Anything else holds nothing.
  expect(park.splitParkResult({ redeemed: { shards: 1 } }, prev)).toEqual({ status: null, park: null });
  expect(park.splitParkResult(null, prev)).toEqual({ status: null, park: null });
});

it("runs park requests in the desk, applies the answers and hands back the server's error code", async () => {
  const calls: string[] = [];
  let coins = 3;
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    calls.push(`${init?.method} ${path}`);
    if (path === "/api/park" ) return response(state({ coins }));
    if (path === "/api/park/coins") {
      const { count } = JSON.parse(init!.body as string);
      if (count > 5) return response({ detail: { code: "coin_limit", message: "今天还能买 5 枚" } }, 409);
      coins += count;
      return response({ ...playerStatus({ shards: 5000 - 500 * count }), park: state({ coins }) });
    }
    if (path === "/api/park/gift") return response({ ...playerStatus(), park: state({ coins }), gift: 0 });
    return response(path === "/api/collection" ? { owned: {}, recent: [] } : playerStatus());
  });
  const { player, park } = await load();
  await player.refresh();
  expect(player.status.value?.park?.news).toHaveLength(1);

  expect(await park.loadPark()).toEqual(state());
  expect(park.park.value?.coins).toBe(3);
  expect(await park.buyCoins(2)).toBe(true);
  expect(park.park.value?.coins).toBe(5);
  expect(player.status.value?.shards).toBe(4000);
  expect(player.status.value?.park).toEqual({ coins: 5, news: playerStatus().park!.news });
  expect(park.parkError.value).toBeNull();

  expect(await park.buyCoins(10)).toBe(false);
  expect(park.parkError.value).toMatchObject({ status: 409, code: "coin_limit", message: "今天还能买 5 枚" });
  // A refusal is the park's to show, not the panel-wide error.
  expect(player.error.value).toBe("");
  expect(player.online.value).toBe(true);

  expect(await park.claimGift()).toBe(0);
  const sent = calls.length;
  const tried = await park.parkTry("GET", "/api/me");
  expect(tried).toMatchObject({ ok: false, error: { code: "bad_path" } });
  expect(await park.parkTry("GET", "/api/park/../me")).toMatchObject({ ok: false, error: { code: "bad_path" } });
  expect(calls).toHaveLength(sent);
});

it("forgets the park on another server, and a server without one is not asked", async () => {
  vi.stubGlobal("fetch", async (url: string) => {
    const { hostname, pathname } = new URL(url);
    if (pathname === "/api/park") return response(state());
    if (pathname === "/api/collection") return response({ owned: {}, recent: [] });
    return response(hostname === "a" ? playerStatus() : playerStatus({ park: undefined }));
  });
  const { settings, player, park } = await load();
  await player.refresh();
  await park.loadPark();
  expect(park.park.value).not.toBeNull();
  settings.serverUrl = "http://b";
  expect(park.park.value).toBeNull();
  await player.refresh();
  expect(park.noPark.value).toBe(true);
  expect(await park.loadPark()).toBeNull();
});

it("keeps which news this device has shown, per server", async () => {
  vi.stubGlobal("fetch", async (url: string) =>
    response(new URL(url).pathname === "/api/collection" ? { owned: {}, recent: [] } : playerStatus()));
  const { settings, player, park } = await load();
  await player.refresh();
  expect(park.unseenParkNews.value.map((n) => n.id)).toEqual([1]);
  park.markNewsSeen([1]);
  expect(park.unseenParkNews.value).toEqual([]);
  expect(JSON.parse(saved.get("asoultappo.parkNews.v1")!)).toEqual({ "http://a": [1] });
  // A fresh start remembers it.
  vi.resetModules();
  const again = await load();
  await again.player.refresh();
  expect(again.park.unseenParkNews.value).toEqual([]);
  // Another server's ids are its own.
  again.settings.serverUrl = "http://b";
  await again.player.refresh();
  expect(again.park.unseenParkNews.value.map((n) => n.id)).toEqual([1]);
  void settings;
});
