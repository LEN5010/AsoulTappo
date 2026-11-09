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

async function setup() {
  const { settings } = await import("./settings");
  settings.serverUrl = "http://a";
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
  const { p, settings } = await setup();
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
