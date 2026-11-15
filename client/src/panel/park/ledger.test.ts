import { beforeEach, describe, expect, it, vi } from "vitest";

const parkTry = vi.fn();
vi.mock("../../stores/park", () => ({ parkTry: (...a: unknown[]) => parkTry(...a) }));

const { chinaDay, dayNet, loadLedger, signed, sortItems, sourceLabel } = await import("./ledger");

describe("ledger words and sums", () => {
  it("names every source the server writes, and a generic word for a newer one", () => {
    const known = ["buy", "gift", "redeem", "stamp", "scratch_again", "race_prize", "race_refund", "admin", "scratch", "race", "lottery"];
    for (const s of known) expect(sourceLabel(s)).not.toBe("其他");
    expect(sourceLabel("buy")).toBe("购买");
    expect(sourceLabel("lottery")).toBe("夺宝");
    expect(sourceLabel("something_new")).toBe("其他");
  });

  it("puts gains first and the larger amounts first within each side", () => {
    const items = [
      { source: "scratch", amount: -2, count: 2 },
      { source: "gift", amount: 1, count: 1 },
      { source: "race", amount: -5, count: 1 },
      { source: "buy", amount: 10, count: 10 },
    ];
    expect(sortItems(items).map((i) => i.source)).toEqual(["buy", "gift", "race", "scratch"]);
    expect(items[0]!.source).toBe("scratch");
  });

  it("sums a day and signs amounts with a true minus", () => {
    expect(dayNet({ day: "2026-11-01", items: [{ source: "buy", amount: 5, count: 5 }, { source: "race", amount: -7, count: 1 }] })).toBe(-2);
    expect(signed(1200)).toBe("+1,200");
    expect(signed(-3)).toBe("−3");
    expect(signed(0)).toBe("0");
  });

  it("takes the China day of a time", () => {
    // 2026-11-14 16:00 UTC is 2026-11-15 00:00 in China.
    const t = Date.UTC(2026, 10, 14, 16, 0, 0) / 1000;
    expect(chinaDay(t)).toBe("2026-11-15");
    expect(chinaDay(t - 1)).toBe("2026-11-14");
  });
});

describe("loadLedger", () => {
  beforeEach(() => parkTry.mockReset());

  it("asks the ledger path and passes the answer on", async () => {
    const data = { days: [{ day: "2026-11-01", items: [] }], redeems: [{ code: "ABCD-EFGH-JKMN", ts: 1, shards: 5, coins: 0 }] };
    parkTry.mockResolvedValue({ ok: true, data });
    expect(await loadLedger()).toEqual({ ok: true, data });
    expect(parkTry).toHaveBeenCalledWith("GET", "/api/park/ledger");
  });

  it("gives the server's message, or the offline line when nothing came back", async () => {
    parkTry.mockResolvedValue({ ok: false, error: { status: 404, code: "no_park", message: "这个服务器没有乐园", detail: {} } });
    expect(await loadLedger()).toEqual({ ok: false, message: "这个服务器没有乐园" });
    parkTry.mockResolvedValue({ ok: false, error: { status: 0, code: "desktop", message: "Error: boom", detail: {} } });
    expect(await loadLedger()).toEqual({ ok: false, message: "无法连接服务器" });
  });
});
