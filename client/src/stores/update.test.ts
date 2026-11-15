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

  it("lists announcements newest first and opens the board while one is due", async () => {
    answer = { version: "0.0.1", notes: "", announcements: [
      { id: "a", title: "维护", body: "今晚", since: 100 }, { id: "b", title: "二" }, { id: "c", title: "新", since: 200 }, { title: "no id" },
    ] };
    let u = await import("./update");
    await u.lookForUpdate();
    expect(u.notices.value.map((a) => a.id)).toEqual(["c", "a", "b"]);
    expect(u.dueNotices.value.map((a) => a.id)).toEqual(["c", "a", "b"]);
    expect(u.noticeBoardShown.value).toBe(true);
    // Closing the board closes all of them, also after a restart.
    u.closeNoticeBoard();
    expect(u.dueNotices.value).toEqual([]);
    expect(u.noticeBoardShown.value).toBe(false);
    vi.resetModules();
    u = await import("./update");
    await u.lookForUpdate();
    expect(u.dueNotices.value).toEqual([]);
    expect(u.noticeBoardShown.value).toBe(false);
    // The top bar opens it again; closing it changes nothing more.
    u.openNoticeBoard();
    expect(u.noticeBoardShown.value).toBe(true);
    u.closeNoticeBoard();
    expect(u.noticeBoardShown.value).toBe(false);
  });

  it("waits for the update dialog and stays shut with nothing to show", async () => {
    answer = { version: "9.9.9", notes: "", announcements: [{ id: "a", title: "维护", body: "" }] };
    let u = await import("./update");
    await u.lookForUpdate();
    expect(u.updateDialogOpen.value).toBe(true);
    expect(u.noticeBoardShown.value).toBe(false);
    u.dismissUpdate();
    expect(u.noticeBoardShown.value).toBe(true);
    vi.resetModules();
    answer = { version: "0.0.1", notes: "", announcements: [] };
    u = await import("./update");
    await u.lookForUpdate();
    u.openNoticeBoard();
    expect(u.noticeBoardShown.value).toBe(false);
  });

  it("brings a daily announcement back the next China day until it is turned off", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    // 23:00 on 11-14 in China.
    vi.setSystemTime(Date.UTC(2026, 10, 14, 15, 0));
    answer = { version: "0.0.1", notes: "", announcements: [{ id: "d", title: "每天", body: "", daily: true }] };
    let u = await import("./update");
    await u.lookForUpdate();
    expect(u.dueNotices.value.map((a) => a.id)).toEqual(["d"]);
    u.closeNoticeBoard();
    expect(u.dueNotices.value).toEqual([]);
    expect(u.noticeSeen("d")).toBe(false);
    // The list comes again after midnight: due again, also after a restart.
    vi.setSystemTime(Date.UTC(2026, 10, 14, 16, 30));
    vi.resetModules();
    u = await import("./update");
    await u.lookForUpdate();
    expect(u.dueNotices.value.map((a) => a.id)).toEqual(["d"]);
    u.readNotice("d");
    expect(u.dueNotices.value).toEqual([]);
    vi.setSystemTime(Date.UTC(2026, 10, 16, 1, 0));
    await u.lookForUpdate(false, true);
    expect(u.dueNotices.value).toEqual([]);
    vi.useRealTimers();
  });

  it("dates announcements by the China day, with the year only when it is not this one", async () => {
    const u = await import("./update");
    const now = Date.UTC(2026, 10, 15, 4, 0);
    // 16:30 UTC on 11-14 is 00:30 on 11-15 in China.
    expect(u.noticeDate(Date.UTC(2026, 10, 14, 16, 30) / 1000, now)).toBe("11月15日");
    expect(u.noticeDate(Date.UTC(2025, 11, 31, 3, 0) / 1000, now)).toBe("2025年12月31日");
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
