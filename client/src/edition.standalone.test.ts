// The standalone edition (src/edition.ts), run with __STANDALONE__ true: npm run test:standalone.
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { copyPacks, listFiles, PACK_KINDS, PACKS_DIR, tempDir } from "../standalone-packs.js";
import viteConfig from "../vite.config";

const calls = { fetch: [] as string[], sockets: [] as string[] };
// Every request any store could make lands here: in the standalone edition there must be none.
const fakeFetch = vi.fn((input: RequestInfo | URL) => {
  calls.fetch.push(String(input));
  return Promise.resolve(new Response("{}", { status: 200 }));
});
class FakeSocket {
  constructor(url: string) {
    calls.sockets.push(url);
  }
  close() {}
  send() {}
}

beforeAll(() => {
  vi.stubGlobal("fetch", fakeFetch);
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => {
  calls.fetch.length = 0;
  calls.sockets.length = 0;
});

describe("standalone edition", () => {
  it("is on in this run", async () => {
    const { STANDALONE } = await import("./edition");
    expect(STANDALONE).toBe(true);
  });

  it("makes no request and opens no socket over two minutes of use", async () => {
    vi.useFakeTimers();
    try {
      const { settings } = await import("./stores/settings");
      const { agree } = await import("./legal/consent");
      const player = await import("./stores/player");
      const room = await import("./stores/room");
      const update = await import("./stores/update");
      const park = await import("./stores/park");
      const { onInput } = await import("./stores/pet");
      const { counter } = await import("./stores/counter");
      const { economy } = await import("./stores/economy");
      expect(settings.serverUrl).toBe("");
      agree();
      // What the desk and the panel start (App.vue, MainPanel.vue, SettingsPage.vue), and what a hidden page would ask.
      player.startReporting();
      const stopRelease = update.watchRelease();
      await update.lookForUpdate(true);
      await player.refreshAccount();
      await player.loadEconomy();
      await park.loadPark();
      room.joinRoom("TAPPO1");
      await room.loadPublicRooms();
      await expect(room.createRoom()).rejects.toThrow();
      const before = counter.total;
      for (let s = 0; s < 120; s++) {
        for (let i = 0; i < 20; i++) onInput({ kind: "key_down", injected: true });
        await vi.advanceTimersByTimeAsync(1000);
      }
      stopRelease();
      player.stopReporting();
      await vi.runOnlyPendingTimersAsync();
      expect(calls).toEqual({ fetch: [], sockets: [] });
      // Every tap counts, auto clickers included: no guard, no cooldown.
      expect(counter.total - before).toBe(2400);
      expect([player.status.value, player.online.value, player.error.value, economy.value]).toEqual([null, false, "", null]);
      expect(room.inRoom.value).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("owns every item of the catalogue from the start", async () => {
    const { manifest } = await import("./manifest");
    const { ownsCharacter, ownsEmote, craftCost, items } = await import("./items");
    const { ownsHolo } = await import("./cards");
    const { allPlates, plateUnlocked } = await import("./pet/plates");
    const { characterNames } = await import("./characters");
    const { collection, status } = await import("./stores/player");
    const owned = collection.owned;
    expect(status.value).toBeNull();
    expect(characterNames.filter((n) => !ownsCharacter(n, owned))).toEqual([]);
    expect(manifest.skins.filter((s) => !ownsCharacter(s.name, owned))).toEqual([]);
    const emotes = manifest.emoteSets.flatMap((s) => s.emotes);
    expect(emotes.filter((e) => !ownsEmote(e.key, owned))).toEqual([]);
    // 阿草's set, won from scratch cards online, is there too.
    expect(manifest.emoteSets.some((s) => s.source === "scratch")).toBe(true);
    expect(manifest.cards.filter((c) => !owned[`card:${c.id}`]).map((c) => c.id)).toEqual([]);
    expect(manifest.cards.some((c) => c.rarity === "limited")).toBe(true);
    const holo = manifest.cards.filter((c) => c.holo);
    expect(holo.length).toBeGreaterThan(0);
    expect(holo.filter((c) => !ownsHolo(c, owned))).toEqual([]);
    expect(allPlates().filter((p) => !plateUnlocked(p.id, owned)).map((p) => p.id)).toEqual([]);
    // Nothing is offered for shards.
    expect(items.filter((i) => craftCost(i) !== null)).toEqual([]);
  });

  it("shows only the backpack, the album and the settings", async () => {
    const { STANDALONE_PAGES, ui, openPanel } = await import("./stores/ui");
    expect(STANDALONE_PAGES).toEqual(["emotes", "dex", "settings"]);
    expect(ui.page).toBe("emotes");
    for (const page of ["resonance", "checkin", "park", "room", "cheer"] as const) {
      openPanel(page);
      expect(ui.page).toBe("emotes");
    }
    openPanel("dex");
    expect(ui.page).toBe("dex");
    ui.page = "settings";
    expect(ui.page).toBe("settings");
  });

  it("refuses server and external addresses at the entry points and lets the app's own files through", async () => {
    const { isLocalUrl, localFetch, refuseServer, serverFetch, StandaloneRefused } = await import("./edition");
    const here = "tauri://localhost/index.html";
    vi.stubGlobal("location", { href: here });
    try {
      expect(isLocalUrl("/assets/emotes/x.webp", here)).toBe(true);
      expect(isLocalUrl("tauri://localhost/packs/cards/a.webp", here)).toBe(true);
      expect(isLocalUrl("blob:tauri://localhost/123", here)).toBe(true);
      // tauri:// has no origin of its own ("null"): another custom scheme must not pass for it.
      expect(isLocalUrl("other://localhost/x", here)).toBe(false);
      expect(isLocalUrl("https://len5010.top/tappo/api/me", here)).toBe(false);
      expect(isLocalUrl("http://tauri.localhost/x", "http://tauri.localhost/index.html")).toBe(true);

      for (const url of ["https://len5010.top/tappo/api/me", "wss://len5010.top/tappo/ws", "/api/me", "/rooms", "/ws?x=1"]) {
        expect(() => refuseServer(url)).toThrow(StandaloneRefused);
        await expect(serverFetch(url)).rejects.toThrow(StandaloneRefused);
      }
      await expect(localFetch("https://example.com/a.webp")).rejects.toThrow(StandaloneRefused);
      expect(calls.fetch).toEqual([]);

      // The app's own files: the bundled assets, the bundled packs.
      await localFetch("/assets/emotes/a.webp");
      await localFetch("tauri://localhost/packs/holo/b.webp", { headers: { Range: "bytes=0-0" } });
      expect(calls.fetch).toEqual(["/assets/emotes/a.webp", "tauri://localhost/packs/holo/b.webp"]);

      // The stores' own clients: an empty server base would be the app's origin, and is refused all the same.
      calls.fetch.length = 0;
      const { Api } = await import("./net/api");
      const { MainAccountApi } = await import("./net/mainAccount");
      await expect(new Api(() => "", () => "token-token-token").me()).rejects.toThrow();
      await expect(new MainAccountApi("https://len5010.top").revoke("t")).rejects.toThrow();
      const { RoomClient } = await import("./net/RoomClient");
      const events = new Proxy({}, { get: () => () => {} }) as ConstructorParameters<typeof RoomClient>[0];
      const client = new RoomClient(events);
      client.join("wss://len5010.top/tappo", { room: "TAPPO1", nick: "n", character: "嘉然", token: "t".repeat(16) });
      client.leave();
      expect(calls).toEqual({ fetch: [], sockets: [] });
    } finally {
      vi.unstubAllGlobals();
      vi.stubGlobal("fetch", fakeFetch);
      vi.stubGlobal("WebSocket", FakeSocket);
    }
  });

  it("keeps its statement apart from the online edition's", async () => {
    const { settings } = await import("./stores/settings");
    const { agree, agreed } = await import("./legal/consent");
    const { STANDALONE_STATEMENT, TERMS_VERSION } = await import("./legal");
    const { APP_VERSION } = await import("./version");
    expect(STANDALONE_STATEMENT).toContain("单机版");
    settings.standaloneStatementSeen = "";
    settings.termsAgreed = TERMS_VERSION;
    settings.statementSeen = APP_VERSION;
    // The online edition's confirmation does not count here.
    expect(agreed.value).toBe(false);
    settings.termsAgreed = "";
    settings.statementSeen = "";
    agree();
    expect([settings.standaloneStatementSeen, settings.statementSeen, settings.termsAgreed]).toEqual([APP_VERSION, "", ""]);
    expect(agreed.value).toBe(true);
    // Asked again by the next version.
    settings.standaloneStatementSeen = "0.0.1-older";
    expect(agreed.value).toBe(false);
  });
});

describe("standalone packs", () => {
  const packFiles = new Set(Object.keys(import.meta.glob("../../assets-packs/{cards,holo,plates,themes}/**/*"))
    .map((p) => p.replace("../../assets-packs/", "")));

  it("resolves every pack: reference of the manifest to a bundled file that exists in assets-packs", async () => {
    const { manifest, resolveAsset } = await import("./manifest");
    const refs: string[] = [];
    const walk = (v: unknown) => {
      if (typeof v === "string" && v.startsWith("pack:")) refs.push(v);
      else if (v && typeof v === "object") Object.values(v).forEach(walk);
    };
    walk(manifest);
    // Card art, holo masks, 衣橱 plate stills and theme parts.
    expect(refs.length).toBeGreaterThan(200);
    for (const ref of refs) {
      const path = ref.slice("pack:".length);
      expect(resolveAsset(ref, "", "/")).toBe(`/packs/${path}`);
      expect(resolveAsset(ref, "https://len5010.top/tappo", "/")).toBe(`/packs/${path}`);
      expect(packFiles.has(path), path).toBe(true);
    }
    const { assetUrl } = await import("./asset");
    const card = manifest.cards.find((c) => c.holo)!;
    expect([assetUrl(card.full), assetUrl(card.holo!.mask)]).toEqual([`/packs/${card.full.slice(5)}`, `/packs/${card.holo!.mask.slice(5)}`]);
  });

  it("copies every pack file into the build output", () => {
    const out = tempDir();
    copyPacks(out);
    const copied = listFiles(`${out}/packs`);
    const source = PACK_KINDS.flatMap((kind) => listFiles(`${PACKS_DIR}/${kind}`).map((f) => `${kind}/${f}`)).sort();
    expect(copied).toEqual(source);
    expect(copied.length).toBe(packFiles.size);
    for (const spot of ["holo/c1781070981002.webp", "plates/wardrobe-jiaran.webp", "themes/beila-2-0/head_bg.webp"]) {
      expect(copied).toContain(spot);
    }
  });

  it("copies them only in the standalone build", () => {
    const names = (mode: string) => {
      const config = (viteConfig as (env: { mode: string; command: "build" }) => { plugins: { name?: string }[] })({ mode, command: "build" });
      return config.plugins.flat().map((p) => p?.name);
    };
    expect(names("standalone")).toContain("asoultappo-standalone-packs");
    expect(names("production")).not.toContain("asoultappo-standalone-packs");
  });
});
