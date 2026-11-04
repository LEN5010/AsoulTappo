import { afterEach, beforeEach, expect, it, vi } from "vitest";

let player: typeof import("./player") | undefined;
const response = (data: unknown) => ({ ok: true, json: async () => data }) as Response;
const statusFor = (server: string) => ({ boxes: server === "a" ? 5 : 0 });
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
  expect(p.status.value?.boxes).toBe(0);
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
  expect(p.status.value?.boxes).toBe(0);
  expect(p.collection.owned).toEqual({ b: 1 });
});

it("discards a draw result after switching servers", async () => {
  let release!: (r: Response) => void;
  vi.stubGlobal("fetch", async (url: string) => {
    if (url.endsWith("/cards/draw")) return new Promise<Response>((resolve) => { release = resolve; });
    const server = new URL(url).hostname;
    return response(url.endsWith("/collection") ? collectionFor(server) : statusFor(server));
  });
  const { settings, p } = await setup();
  await vi.advanceTimersByTimeAsync(0);
  const draw = p.drawCards("bloom");
  await vi.advanceTimersByTimeAsync(0);
  settings.serverUrl = "http://b";
  await vi.advanceTimersByTimeAsync(0);
  release(response({ boxes: 5, drops: [] }));
  expect(await draw).toBeNull();
  expect(p.status.value?.boxes).toBe(0);
});

it("reports running time even when there are no key presses", async () => {
  const heartbeats: string[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url.endsWith("/presence")) heartbeats.push(JSON.parse(init!.body as string).session);
    return response(url.endsWith("/collection") ? { owned: {}, recent: [] } : {
      boxes: 0, draw: { tickets: 2, seconds: 100, pity: 3, hardPity: 400, total: 3, secondsPerDraw: 300 },
    });
  });
  const { p } = await setup();
  await vi.advanceTimersByTimeAsync(40000);
  expect(heartbeats).toHaveLength(3);
  expect(new Set(heartbeats).size).toBe(1);
  expect(p.tickets.value).toBe(2);
  p.stopReporting();
  await vi.advanceTimersByTimeAsync(40000);
  expect(heartbeats).toHaveLength(3);
});
