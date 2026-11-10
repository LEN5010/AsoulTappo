import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The server's answer to the update check also carries its minimum version and announcements.
describe("minimum version and announcements", () => {
  let answer: Record<string, unknown>;
  const stored = new Map<string, string>();
  beforeEach(() => {
    vi.resetModules();
    stored.clear();
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
});
