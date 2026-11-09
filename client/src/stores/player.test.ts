import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { plateCard, plateSet } from "../pet/plates";

let player: typeof import("./player") | undefined;
const response = (data: unknown) => ({ ok: true, json: async () => data }) as Response;
const statusFor = (server: string) => ({ shards: server === "a" ? 800 : 0 });
const collectionFor = (server: string) => ({ owned: { [server]: 1 }, recent: [] });

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
});
afterEach(async () => {
  player?.stopReporting();
  await vi.advanceTimersByTimeAsync(0);
  player = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function setup(server = "http://a") {
  const { settings } = await import("./settings");
  settings.serverUrl = server;
  player = await import("./player");
  player.startReporting();
  return { settings, p: player };
}

it("signing in moves new input to the account save while pending input stays with the guest save", async () => {
  const activities: string[] = [];
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() });
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const headers = init!.headers as Record<string, string>;
    if (url.endsWith("/activity")) activities.push(headers.Authorization ?? headers["X-Player-Token"]!);
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : { shards: 0 });
  });
  // Account tokens only go to trusted servers; tests run as a dev build, which trusts localhost.
  const { p, settings } = await setup("http://localhost:1");
  await vi.advanceTimersByTimeAsync(0);
  const guest = p.token;
  p.countInput();
  await p.setAccount({ server: settings.serverUrl, token: "acct", user: { id: "u", username: "alice", email: "a@example.com" } }, true);
  p.countInput();
  await vi.advanceTimersByTimeAsync(20000);
  expect(p.token).not.toBe(guest);
  expect(activities).toEqual([guest, "Bearer acct"]);
});

it("keeps pending batches and their retries at the original server", async () => {
  const activities: { url: string; body: unknown }[] = [];
  let failA = true;
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const server = new URL(url).hostname;
    if (url.endsWith("/activity")) {
      activities.push({ url, body: JSON.parse(init!.body as string) });
      if (server === "a" && failA) { failA = false; throw new TypeError("offline"); }
    }
    return response(url.endsWith("/collection") ? collectionFor(server) : statusFor(server));
  });
  const { settings, p } = await setup();
  await vi.advanceTimersByTimeAsync(0);
  expect(p.collection.owned).toEqual({ a: 1 });
  p.countInput();
  settings.serverUrl = "http://b";
  expect(p.status.value).toBeNull();
  expect(p.collection.owned).toEqual({});
  await vi.advanceTimersByTimeAsync(0);
  expect(p.online.value).toBe(true);
  p.countInput(); p.countInput();
  await vi.advanceTimersByTimeAsync(20000);
  expect(activities.map((r) => r.url)).toEqual(["http://a/api/activity", "http://a/api/activity", "http://b/api/activity"]);
  expect(activities[0]).toEqual(activities[1]);
  expect(activities[2].body).toMatchObject({ taps: 2, sequence: 1 });
  expect(p.status.value?.shards).toBe(0);
  expect(p.collection.owned).toEqual({ b: 1 });
});

it("ignores a previous server's slow refresh after switching", async () => {
  let release!: (r: Response) => void;
  const slow = new Promise<Response>((resolve) => { release = resolve; });
  vi.stubGlobal("fetch", async (url: string) => {
    if (url === "http://a/api/me") return slow;
    const server = new URL(url).hostname;
    return response(url.endsWith("/collection") ? collectionFor(server) : statusFor(server));
  });
  const { settings, p } = await setup();
  settings.serverUrl = "http://b";
  await vi.advanceTimersByTimeAsync(0);
  release(response(statusFor("a")));
  await vi.advanceTimersByTimeAsync(0);
  expect(p.status.value?.shards).toBe(0);
  expect(p.collection.owned).toEqual({ b: 1 });
});

it("discards a draw result after switching servers", async () => {
  let release!: (r: Response) => void;
  vi.stubGlobal("fetch", async (url: string) => {
    if (url.endsWith("/resonance/draw")) return new Promise<Response>((resolve) => { release = resolve; });
    const server = new URL(url).hostname;
    return response(url.endsWith("/collection") ? collectionFor(server) : statusFor(server));
  });
  const { settings, p } = await setup();
  await vi.advanceTimersByTimeAsync(0);
  const draw = p.resonate();
  await vi.advanceTimersByTimeAsync(0);
  settings.serverUrl = "http://b";
  await vi.advanceTimersByTimeAsync(0);
  release(response({ shards: 800, drops: [] }));
  expect(await draw).toBeNull();
  expect(p.status.value?.shards).toBe(0);
});

it("reports running time even when there are no key presses", async () => {
  const heartbeats: string[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url.endsWith("/presence")) heartbeats.push(JSON.parse(init!.body as string).session);
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : {
      shards: 320,
    });
  });
  const { p } = await setup();
  await vi.advanceTimersByTimeAsync(40000);
  expect(heartbeats).toHaveLength(3);
  expect(new Set(heartbeats).size).toBe(1);
  expect(p.draws.value).toBe(2);
  p.stopReporting();
  await vi.advanceTimersByTimeAsync(40000);
  expect(heartbeats).toHaveLength(3);
});

it("equips an original member when a saved skin is locked after collection loads", async () => {
  vi.stubGlobal("fetch", async (url: string) => response(url.endsWith("/collection") ? { owned: {}, recent: [] } : { shards: 1600 }));
  const { settings, p } = await setup();
  settings.character = "贝拉山海经";
  await vi.advanceTimersByTimeAsync(0);
  expect(settings.character).toBe("贝拉");
  settings.character = "贝拉山海经";
  p.online.value = false;
  p.sanitizeLoadout();
  expect(settings.character).toBe("贝拉山海经");
  p.online.value = true;
  p.collection.owned["char:贝拉山海经"] = 1;
  p.sanitizeLoadout();
  expect(settings.character).toBe("贝拉山海经");
});

it("takes off a plate whose set is not collected and sends the one that is", async () => {
  const sent: unknown[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url.endsWith("/loadout") && init?.body) sent.push(JSON.parse(String(init.body)));
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : { shards: 1600 });
  });
  const { settings, p } = await setup();
  settings.plate = "c1762331462002";
  await vi.advanceTimersByTimeAsync(0);
  expect(settings.plate).toBe("");
  // The big hidden card alone no longer unlocks its plate.
  p.collection.owned["card:c1762331462002"] = 1;
  settings.plate = "c1762331462002";
  p.sanitizeLoadout();
  expect(settings.plate).toBe("");
  for (const c of plateSet(plateCard("c1762331462002")!)) p.collection.owned[`card:${c.id}`] = 1;
  settings.plate = "c1762331462002";
  p.sanitizeLoadout();
  expect(settings.plate).toBe("c1762331462002");
  await vi.advanceTimersByTimeAsync(500);
  expect(sent.at(-1)).toMatchObject({ plate: "c1762331462002" });
});

// ---------------------------------------------------------------- loadout ownership
const OWNER = "asoultappo.loadoutOwner.v1";
function memoryStorage(initial: Record<string, string> = {}) {
  const saved = new Map(Object.entries(initial));
  return {
    saved,
    getItem: (k: string) => saved.get(k) ?? null,
    setItem: (k: string, v: string) => void saved.set(k, v),
    removeItem: (k: string) => void saved.delete(k),
  };
}
function loadoutServer(stored: unknown, failPull = false, pullGate: Promise<void> = Promise.resolve()) {
  const calls: string[] = [];
  const pushed: Record<string, unknown>[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url.endsWith("/loadout")) {
      if (init?.method === "POST") {
        calls.push("push");
        pushed.push(JSON.parse(String(init.body)));
        return response(stored);
      }
      calls.push("pull");
      await pullGate;
      return failPull ? ({ ok: false, status: 500, json: async () => ({}) } as Response) : response(stored);
    }
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : { player: "p1", shards: 0 });
  });
  return { calls, pushed };
}

it("pushes the local loadout to the save it belongs to", async () => {
  vi.stubGlobal("localStorage", memoryStorage({ [OWNER]: "http://a|p1" }));
  const { calls, pushed } = loadoutServer({ character: "贝拉", favorites: [], plate: null });
  const { settings } = await setup();
  settings.character = "乃琳";
  await vi.advanceTimersByTimeAsync(500);
  expect(calls).toEqual(["push"]);
  expect(pushed[0]).toMatchObject({ character: "乃琳" });
  expect(settings.character).toBe("乃琳");
});

it("loads the stored loadout of another save instead of pushing the local one to it", async () => {
  const storage = memoryStorage({ [OWNER]: "http://a|old" });
  vi.stubGlobal("localStorage", storage);
  const { starterEmotesOf } = await import("../items");
  const favorites = starterEmotesOf("贝拉").slice(0, 2);
  const { calls, pushed } = loadoutServer({ character: "贝拉", favorites, plate: null });
  const { settings } = await setup();
  settings.character = "乃琳";
  await vi.advanceTimersByTimeAsync(500);
  expect(calls).toEqual(["pull"]);
  expect(settings.character).toBe("贝拉");
  expect(settings.favorites).toEqual(favorites);
  expect(storage.saved.get(OWNER)).toBe("http://a|p1");
  // From now on local changes belong to this save.
  settings.character = "嘉然";
  await vi.advanceTimersByTimeAsync(500);
  expect(calls).toEqual(["pull", "push"]);
  expect(pushed[0]).toMatchObject({ character: "嘉然" });
});

it("does not push local changes to another save while its loadout is loading", async () => {
  vi.stubGlobal("localStorage", memoryStorage({ [OWNER]: "http://a|old" }));
  let release!: () => void;
  const { calls } = loadoutServer({ character: "贝拉", favorites: [], plate: null }, false, new Promise((r) => { release = r; }));
  const { settings } = await setup();
  await vi.advanceTimersByTimeAsync(0);
  expect(calls).toEqual(["pull"]);
  settings.character = "乃琳";
  await vi.advanceTimersByTimeAsync(500);
  expect(calls).toEqual(["pull"]);
  release();
  await vi.advanceTimersByTimeAsync(500);
  expect(calls).toEqual(["pull"]);
  expect(settings.character).toBe("贝拉");
});

it("a save that never chose a character keeps the member of the local one", async () => {
  vi.stubGlobal("localStorage", memoryStorage({ [OWNER]: "http://a|old" }));
  loadoutServer({ character: null, favorites: [], plate: null });
  const { settings } = await setup();
  settings.character = "贝拉山海经";
  await vi.advanceTimersByTimeAsync(0);
  expect(settings.character).toBe("贝拉");
});

it("pushes nothing to another save when its loadout cannot be loaded", async () => {
  const storage = memoryStorage({ [OWNER]: "http://a|old" });
  vi.stubGlobal("localStorage", storage);
  const { calls } = loadoutServer(null, true);
  const { settings } = await setup();
  settings.character = "乃琳";
  await vi.advanceTimersByTimeAsync(500);
  settings.character = "嘉然";
  await vi.advanceTimersByTimeAsync(500);
  expect(calls.length).toBeGreaterThan(0);
  expect(calls.every((c) => c === "pull")).toBe(true);
  expect(storage.saved.get(OWNER)).toBe("http://a|old");
});

it("tries again after a heartbeat when another save's loadout could not be loaded", async () => {
  const storage = memoryStorage({ [OWNER]: "http://a|old" });
  vi.stubGlobal("localStorage", storage);
  let fail = true;
  let pulls = 0;
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url.endsWith("/loadout") && init?.method !== "POST") {
      pulls++;
      return fail ? ({ ok: false, status: 500, json: async () => ({}) } as Response) : response({ character: "贝拉", favorites: [], plate: null });
    }
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : { player: "p1", shards: 0 });
  });
  const { settings } = await setup();
  settings.character = "乃琳";
  await vi.advanceTimersByTimeAsync(500);
  expect(storage.saved.get(OWNER)).toBe("http://a|old");
  fail = false;
  const before = pulls;
  await vi.advanceTimersByTimeAsync(20000);
  expect(pulls).toBe(before + 1);
  expect(settings.character).toBe("贝拉");
  expect(storage.saved.get(OWNER)).toBe("http://a|p1");
});

it("the first run adopts the current save and keeps the local loadout", async () => {
  const storage = memoryStorage();
  vi.stubGlobal("localStorage", storage);
  const { calls, pushed } = loadoutServer({ character: "贝拉", favorites: [], plate: null });
  const { settings } = await setup();
  settings.character = "乃琳";
  await vi.advanceTimersByTimeAsync(500);
  expect(calls).toEqual(["push"]);
  expect(pushed[0]).toMatchObject({ character: "乃琳" });
  expect(storage.saved.get(OWNER)).toBe("http://a|p1");
});

it("never uses a stored account session on an untrusted server", async () => {
  const session = { server: "http://a", token: "acct", user: { id: "u", username: "alice", email: null } };
  vi.stubGlobal("localStorage", memoryStorage({ "asoultappo.account.v1": JSON.stringify(session) }));
  const auth: string[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const headers = init!.headers as Record<string, string>;
    auth.push(headers.Authorization ?? "guest");
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : { player: "p1", shards: 0 });
  });
  const { p } = await setup();
  await vi.advanceTimersByTimeAsync(0);
  expect(p.account.value?.token).toBe("acct");
  expect(p.activeAccount()).toBeNull();
  expect(auth.length).toBeGreaterThan(0);
  expect(auth.every((a) => a === "guest")).toBe(true);
});
