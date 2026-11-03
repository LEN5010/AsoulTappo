import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, loadSettings } from "./settings";

const store = (v: string | null) => ({ getItem: () => v });

describe("loadSettings", () => {
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
});
