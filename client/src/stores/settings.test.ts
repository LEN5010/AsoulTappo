import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, loadSettings } from "./settings";

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
  it("keeps a room status only when it is one of the list", () => {
    expect(loadSettings(store(JSON.stringify({ status: "fish" }))).status).toBe("fish");
    expect(loadSettings(store(JSON.stringify({ status: "chat" }))).status).toBe("");
  });
  it("keeps a capture background only as a six-digit hex colour and the capture size within limits", () => {
    expect(loadSettings(store(JSON.stringify({ captureBg: "#0000FF" }))).captureBg).toBe("#0000FF");
    expect(loadSettings(store(JSON.stringify({ captureBg: "url(x)" }))).captureBg).toBe("#00ff00");
    expect(loadSettings(store(JSON.stringify({ captureW: 9000, captureH: 12.4 })))).toMatchObject({ captureW: 1600, captureH: 160 });
  });
});
