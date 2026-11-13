import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TERMS_VERSION } from "../legal";

// The server's answer to the update check also carries its minimum version and announcements.
describe("minimum version and announcements", () => {
  let answer: Record<string, unknown>;
  const stored = new Map<string, string>();
  beforeEach(() => {
    vi.resetModules();
    stored.clear();
    stored.set("asoultappo.settings.v1", JSON.stringify({ termsAgreed: TERMS_VERSION }));
    vi.stubGlobal("localStorage", { getItem: (k: string) => stored.get(k) ?? null, setItem: (k: string, v: string) => stored.set(k, v) });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => answer })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the dialog open while this version is below the minimum", async () => {
    answer = { version: "99.0.0", notes: "", minVersion: "99.0.0" };
    const u = await import("./update");
    await u.lookForUpdate();
    expect(u.updateForced.value).toBe(true);
    expect(u.updateDialogOpen.value).toBe(true);
    u.dismissUpdate();
    expect(u.updateDialogOpen.value).toBe(true);
  });

  it("offers the update as before when the minimum is met", async () => {
    answer = { version: "99.0.0", notes: "", minVersion: "0.0.1" };
    const u = await import("./update");
    await u.lookForUpdate();
    expect(u.updateForced.value).toBe(false);
    expect(u.updateDialogOpen.value).toBe(true);
    u.dismissUpdate();
    expect(u.updateDialogOpen.value).toBe(false);
    // Dismissed for this version: the watch asking again does not reopen it.
    await u.lookForUpdate(false, true);
    expect(u.updateDialogOpen.value).toBe(false);
  });

  it("shows each announcement until it is closed, and remembers that", async () => {
    answer = { version: "0.0.1", notes: "", announcements: [{ id: "a", title: "维护", body: "今晚" }, { id: "b", title: "二" }, { title: "no id" }] };
    let u = await import("./update");
    await u.lookForUpdate();
    expect(u.unreadNotice.value).toEqual({ id: "a", title: "维护", body: "今晚" });
    u.readNotice("a");
    expect(u.unreadNotice.value?.id).toBe("b");
    u.readNotice("b");
    expect(u.unreadNotice.value).toBeNull();
    vi.resetModules();
    u = await import("./update");
    await u.lookForUpdate();
    expect(u.unreadNotice.value).toBeNull();
  });

  it("shows a daily announcement again the next China day until it is turned off", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    // 23:00 on 11-14 in China.
    vi.setSystemTime(Date.UTC(2026, 10, 14, 15, 0));
    answer = { version: "0.0.1", notes: "", announcements: [{ id: "d", title: "每天", body: "", daily: true }] };
    let u = await import("./update");
    await u.lookForUpdate();
    expect(u.unreadNotice.value?.id).toBe("d");
    u.closeNotice(u.unreadNotice.value!);
    expect(u.unreadNotice.value).toBeNull();
    // The list comes again after midnight: due again, also after a restart.
    vi.setSystemTime(Date.UTC(2026, 10, 14, 16, 30));
    vi.resetModules();
    u = await import("./update");
    await u.lookForUpdate();
    expect(u.unreadNotice.value?.id).toBe("d");
    u.readNotice("d");
    expect(u.unreadNotice.value).toBeNull();
    vi.setSystemTime(Date.UTC(2026, 10, 16, 1, 0));
    await u.lookForUpdate(false, true);
    expect(u.unreadNotice.value).toBeNull();
    vi.useRealTimers();
  });
});

describe("before the terms are agreed", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks nothing until the player agrees, then checks at once", async () => {
    vi.resetModules();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
    const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ version: "0.0.1", notes: "" }) }));
    vi.stubGlobal("fetch", fetch);
    const { settings } = await import("./settings");
    const u = await import("./update");
    const stop = u.watchRelease();
    await u.lookForUpdate();
    expect(fetch).not.toHaveBeenCalled();
    settings.termsAgreed = TERMS_VERSION;
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    stop();
  });
});
