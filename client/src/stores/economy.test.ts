import { afterEach, describe, expect, it, vi } from "vitest";
import { ECONOMY_KEY, exampleEconomy, withEconomy } from "../test/economy";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

async function fresh(entries: Record<string, string> = {}) {
  const stored = new Map(Object.entries(entries));
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => stored.get(k) ?? null,
    setItem: (k: string, v: string) => stored.set(k, v),
    removeItem: (k: string) => stored.delete(k),
  });
  vi.resetModules();
  const { settings } = await import("./settings");
  const store = await import("./economy");
  return { settings, store, stored };
}

describe("economy", () => {
  it("is unknown until a server answers, then kept for that server only", async () => {
    const { settings, store, stored } = await fresh();
    settings.serverUrl = "http://a";
    expect(store.economy.value).toBeNull();
    store.setEconomy(exampleEconomy);
    expect(store.economy.value?.resonance.cost).toBe(exampleEconomy.resonance.cost);
    expect(JSON.parse(stored.get(ECONOMY_KEY)!).server).toBe("http://a");
    settings.serverUrl = "http://b";
    expect(store.economy.value).toBeNull();
    settings.serverUrl = "http://a";
    expect(store.economy.value).not.toBeNull();
  });

  it("starts from the copy kept for the current server", async () => {
    const { store } = await fresh({ [ECONOMY_KEY]: withEconomy(() => null)(ECONOMY_KEY)! });
    expect(store.economy.value?.income.dailyCap).toBe(exampleEconomy.income.dailyCap);
    expect(store.economyDue()).toBe(false);
    expect(store.economyDue(Date.now() + store.ECONOMY_MAX_AGE_MS)).toBe(true);
  });

  it("ignores an answer that is not an economy", async () => {
    const { store } = await fresh();
    store.setEconomy({ shards: 320 } as never);
    expect(store.economy.value).toBeNull();
    expect(store.economyDue()).toBe(true);
  });

  it("refreshes the economy at a known banner end even while the cached prices are fresh", async () => {
    const { store } = await fresh();
    const at = 1_000_000;
    const banner = { id: "b", name: "b", start: 999, end: 1010, items: ["char:嘉然然龙"], rate: 3 };
    const active = { ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [banner], held: banner.items } };
    store.setEconomy(active, undefined, at);
    expect(store.economyDue(1_009_999)).toBe(false);
    expect(store.economyDue(1_010_000)).toBe(true);
    // A clock ahead of the server can get the same banner back; check again without polling every heartbeat.
    store.setEconomy(active, undefined, 1_010_000);
    expect(store.economyDue(1_030_000)).toBe(false);
    expect(store.economyDue(1_070_000)).toBe(true);
    store.setEconomy(exampleEconomy, undefined, 1_070_000);
    expect(store.economyDue(1_090_000)).toBe(false);
  });

  it("writes economy cache to localStorage only in the Tauri main window", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: "?window=panel" } });
    const panel = await fresh();
    panel.store.setEconomy(exampleEconomy);
    expect(panel.store.economy.value?.resonance.cost).toBe(exampleEconomy.resonance.cost);
    expect(panel.stored.has(ECONOMY_KEY)).toBe(false);

    vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: "" } });
    const main = await fresh();
    main.store.setEconomy(exampleEconomy);
    expect(main.stored.has(ECONOMY_KEY)).toBe(true);
  });
});

describe("Api.economy", () => {
  it("falls back to the manifest of servers from before /api/economy", async () => {
    const asked: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      asked.push(new URL(url).pathname);
      return url.endsWith("/api/economy")
        ? new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })
        : new Response(JSON.stringify({ economy: exampleEconomy }), { status: 200 });
    });
    const { Api } = await import("../net/api");
    const got = await new Api(() => "http://old", () => "t".repeat(32)).economy();
    expect(got.scratch.price).toBe(exampleEconomy.scratch.price);
    expect(asked).toEqual(["/api/economy", "/api/manifest"]);
  });

  it("passes other errors on", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: { code: "boom", message: "x" } }), { status: 500 }));
    const { Api, ApiError } = await import("../net/api");
    await expect(new Api(() => "http://old", () => "t".repeat(32)).economy()).rejects.toBeInstanceOf(ApiError);
  });
});
