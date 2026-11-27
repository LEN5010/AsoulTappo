import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { DEFAULT_SETTINGS, loadSettings, partnerNames, setPartnerNames } from "./settings";
import { FEEDBACK_CONTACT_MAX, FEEDBACK_TEXT_MAX } from "./feedback";

const store = (v: string | null) => ({ getItem: () => v });

describe("loadSettings", () => {
  it("moves devices on the old server address to the current one and keeps custom servers", () => {
    expect(loadSettings(store(JSON.stringify({ serverUrl: "http://121.36.224.230:8000" }))).serverUrl).toBe("https://len5010.top/tappo");
    expect(loadSettings(store(JSON.stringify({ serverUrl: "http://127.0.0.1:8010" }))).serverUrl).toBe("http://127.0.0.1:8010");
  });
  it("returns defaults when nothing is stored or JSON is corrupt", () => {
    expect(loadSettings(store(null))).toEqual(DEFAULT_SETTINGS);
    expect(loadSettings(store("{oops"))).toEqual(DEFAULT_SETTINGS);
  });
  it("merges valid stored values, ignores wrong types, clamps ranges", () => {
    const s = loadSettings(store(JSON.stringify({ nick: "bun", scale: 99, batchMs: 5, serverUrl: 42, extra: 1 })));
    expect(s.nick).toBe("bun");
    expect(s.scale).toBe(3);
    expect(s.batchMs).toBe(100);
    expect(s.serverUrl).toBe(DEFAULT_SETTINGS.serverUrl);
    expect("extra" in s).toBe(false);
  });
  it("lets the strip follow the pet unless a size is set for it, within what the settings page offers", () => {
    expect(loadSettings(store(null))).toMatchObject({ barFollow: true, barScale: 1 });
    expect(loadSettings(store(JSON.stringify({ barFollow: false, barScale: 0.1 })))).toMatchObject({ barFollow: false, barScale: 0.6 });
    expect(loadSettings(store(JSON.stringify({ barScale: 9 }))).barScale).toBe(1.5);
    expect(loadSettings(store(JSON.stringify({ barScale: "x" }))).barScale).toBe(1);
  });
  it("shows the pets solid unless set otherwise, and never fainter than the settings page goes", () => {
    expect(loadSettings(store(null)).petOpacity).toBe(1);
    expect(loadSettings(store(JSON.stringify({ petOpacity: 0.55 }))).petOpacity).toBe(0.55);
    expect(loadSettings(store(JSON.stringify({ petOpacity: 0 }))).petOpacity).toBe(0.3);
    expect(loadSettings(store(JSON.stringify({ petOpacity: 4 }))).petOpacity).toBe(1);
    expect(loadSettings(store(JSON.stringify({ petOpacity: "x" }))).petOpacity).toBe(1);
  });
  it("keeps the panel at its old size unless one is set, within what the settings page offers", () => {
    expect(loadSettings(store(null)).panelScale).toBe(1);
    expect(loadSettings(store(JSON.stringify({ panelScale: 0.5 }))).panelScale).toBe(0.9);
    expect(loadSettings(store(JSON.stringify({ panelScale: 3 }))).panelScale).toBe(1.5);
    expect(loadSettings(store(JSON.stringify({ panelScale: "x" }))).panelScale).toBe(1);
  });
  it("keeps only string favorites (at most 8) and never shares the default array", () => {
    const s = loadSettings(store(JSON.stringify({ favorites: ["a", 3, "b", ...Array(10).fill("c")], tapView: "x" })));
    expect(s.favorites).toEqual(["a", "b", "c", "c", "c", "c", "c", "c"]);
    expect(s.tapView).toBe("today");
    loadSettings(store(null)).favorites.push("x");
    expect(DEFAULT_SETTINGS.favorites).toEqual([]);
  });
  it("keeps the name plate up only where the old handle setting let it show", () => {
    expect(loadSettings(store(JSON.stringify({ gripPlate: true, barPlate: true }))).barPlate).toBe(true);
    expect(loadSettings(store(JSON.stringify({ gripPlate: false, barPlate: true }))).barPlate).toBe(false);
    expect(loadSettings(store(JSON.stringify({ barPlate: true }))).barPlate).toBe(true);
    expect("gripPlate" in loadSettings(store(JSON.stringify({ gripPlate: true })))).toBe(false);
  });
  it("reads partner names as nickname, member name or none, and no names wins over member names", () => {
    expect(partnerNames(loadSettings(store(null)))).toBe("nick");
    expect(partnerNames(loadSettings(store(JSON.stringify({ hideNicks: true }))))).toBe("member");
    const off = loadSettings(store(JSON.stringify({ showNames: false, hideNicks: true })));
    expect(partnerNames(off)).toBe("off");
    expect(off.hideNicks).toBe(false);
  });
  it("sets partner names through both switches", () => {
    const s = loadSettings(store(null));
    setPartnerNames(s, "member");
    expect(s).toMatchObject({ showNames: true, hideNicks: true });
    setPartnerNames(s, "off");
    expect(s).toMatchObject({ showNames: false, hideNicks: false });
    setPartnerNames(s, "nick");
    expect(s).toMatchObject({ showNames: true, hideNicks: false });
  });
  it("keeps a room status only when it is one of the list", () => {
    expect(loadSettings(store(JSON.stringify({ status: "fish" }))).status).toBe("fish");
    expect(loadSettings(store(JSON.stringify({ status: "chat" }))).status).toBe("");
  });
  it("keeps the partner layout only as a known mode and the formation columns within 1 to 10", () => {
    expect(loadSettings(store(JSON.stringify({ partnerLayout: "formation", formationCols: 3.6 })))).toMatchObject({
      partnerLayout: "formation", formationCols: 4,
    });
    expect(loadSettings(store(JSON.stringify({ partnerLayout: "grid", formationCols: 40 })))).toMatchObject({
      partnerLayout: "free", formationCols: 10,
    });
    expect(loadSettings(store(JSON.stringify({ formationCols: 0, formationX: -30, formationY: 12.4 })))).toMatchObject({
      formationCols: 1, formationX: -1, formationY: 12,
    });
  });
  it("keeps the row on the bottom edge as a layout, its place a whole pixel or -1", () => {
    expect(loadSettings(store(JSON.stringify({ partnerLayout: "row", partnerRowX: 300.6 })))).toMatchObject({
      partnerLayout: "row", partnerRowX: 301,
    });
    expect(loadSettings(store(JSON.stringify({ partnerRowX: -40 }))).partnerRowX).toBe(-40);
    expect(loadSettings(store("{}")).partnerRowX).toBe(-1);
  });
  it("keeps a capture background only as a six-digit hex colour and the capture size within limits", () => {
    expect(loadSettings(store(JSON.stringify({ captureBg: "#0000FF" }))).captureBg).toBe("#0000FF");
    expect(loadSettings(store(JSON.stringify({ captureBg: "url(x)" }))).captureBg).toBe("#00ff00");
    expect(loadSettings(store(JSON.stringify({ captureW: 9000, captureH: 12.4 })))).toMatchObject({ captureW: 1600, captureH: 160 });
  });
  it("keeps an unsent feedback draft as text, no longer than the server takes", () => {
    expect(loadSettings(store(null))).toMatchObject({ feedbackText: "", feedbackContact: "" });
    expect(loadSettings(store(JSON.stringify({ feedbackText: "卡住了", feedbackContact: "qq 1" })))).toMatchObject({
      feedbackText: "卡住了", feedbackContact: "qq 1",
    });
    const long = loadSettings(store(JSON.stringify({ feedbackText: "a".repeat(5000), feedbackContact: "b".repeat(500) })));
    expect(long.feedbackText).toHaveLength(FEEDBACK_TEXT_MAX);
    expect(long.feedbackContact).toHaveLength(FEEDBACK_CONTACT_MAX);
    expect(loadSettings(store(JSON.stringify({ feedbackText: 3 }))).feedbackText).toBe("");
  });
});

describe("desk settings persistence", () => {
  const key = "asoultappo.settings.v1";
  let page: EventTarget;
  let stored: Map<string, string>;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
    page = new EventTarget();
    vi.stubGlobal("window", Object.assign(page, { __TAURI_INTERNALS__: {}, location: { search: "" } }));
    stored = new Map();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => stored.get(k) ?? null,
      setItem: (k: string, value: string) => stored.set(k, value),
    });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("persists normalized placement, scales, opacity, draft, showcase order and taskbar settings", async () => {
    stored.set(key, JSON.stringify({
      petX: -52, petY: 28, partnerRowX: -80.7, panelScale: 1.35, petOpacity: 0.53,
      feedbackText: "留给明天", feedbackContact: "房主", showcase: ["c", "a", "c", "b"],
      barFolded: true, barFollow: false, barScale: 1.2, rejoinRoom: "last-room",
    }));
    const { settings, loadSettings } = await import("./settings");
    const normalized = {
      petX: -52, petY: 28, partnerRowX: -81, panelScale: 1.35, petOpacity: 0.53,
      feedbackText: "留给明天", feedbackContact: "房主", showcase: ["c", "a", "b"],
      barFolded: true, barFollow: false, barScale: 1.2, rejoinRoom: "last-room",
    };
    expect(settings).toMatchObject(normalized);
    settings.showcase.reverse();
    await vi.advanceTimersByTimeAsync(200);
    const reordered = { ...normalized, showcase: ["b", "a", "c"] };
    expect(JSON.parse(stored.get(key)!)).toMatchObject(reordered);
    expect(loadSettings()).toMatchObject(reordered);
  });

  it("keeps the last of several desk edits when the page is hidden", async () => {
    const { settings } = await import("./settings");
    settings.feedbackText = "草";
    await nextTick();
    settings.feedbackText = "草稿";
    await nextTick();
    settings.feedbackText = "草稿已改";
    await nextTick();
    page.dispatchEvent(new Event("pagehide"));
    expect(JSON.parse(stored.get(key)!).feedbackText).toBe("草稿已改");
  });

  it("writes 200 ms after the last edit and flushes pending edits on hide or close", async () => {
    const doc = Object.assign(new EventTarget(), { hidden: false });
    vi.stubGlobal("document", doc);
    const { settings } = await import("./settings");
    const write = vi.spyOn(stored, "set");
    settings.petX = -20;
    await vi.advanceTimersByTimeAsync(100);
    settings.petX = -35;
    await vi.advanceTimersByTimeAsync(199);
    expect(write).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(write).toHaveBeenCalledTimes(1);
    expect(JSON.parse(stored.get(key)!).petX).toBe(-35);

    settings.petX = -40;
    doc.hidden = true;
    doc.dispatchEvent(new Event("visibilitychange"));
    expect(JSON.parse(stored.get(key)!).petX).toBe(-40);
    settings.petX = -45;
    page.dispatchEvent(new Event("beforeunload"));
    expect(JSON.parse(stored.get(key)!).petX).toBe(-45);
    page.dispatchEvent(new Event("pagehide"));
    await vi.advanceTimersByTimeAsync(200);
    expect(write).toHaveBeenCalledTimes(3);
  });

  it("writes pending edits at once when flushed before a restart, and only once", async () => {
    const { settings, flushSettings } = await import("./settings");
    const write = vi.spyOn(stored, "set");
    settings.petX = -20;
    flushSettings();
    expect(write).toHaveBeenCalledTimes(1);
    expect(JSON.parse(stored.get(key)!).petX).toBe(-20);
    await vi.advanceTimersByTimeAsync(200);
    flushSettings();
    expect(write).toHaveBeenCalledTimes(1);
  });
});
