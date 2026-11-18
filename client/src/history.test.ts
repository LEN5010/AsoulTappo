import { describe, expect, it } from "vitest";
import { byDay, clockOf, dayKey, dayLabel, rowsOf } from "./history";
import { items } from "./items";
import { manifest } from "./manifest";

const at = (y: number, m: number, d: number, h = 12, min = 0) => new Date(y, m - 1, d, h, min).getTime() / 1000;
const card = items.find((i) => i.kind === "card" && i.rarity === "common")!;
const skin = items.find((i) => i.kind === "character" && i.rarity === "skin")!;
const holoCard = manifest.cards.find((c) => c.holo);

describe("rowsOf", () => {
  it("names each drop's item and tier, and where it came from", () => {
    const rows = rowsOf([
      { id: 4, item: skin.id, rarity: "skin", new: true, ts: 40, source: "draw", pool: "forms-1", poolName: "双形态" },
      { id: 3, item: card.id, rarity: "common", new: false, ts: 30, source: "draw" },
      { id: 2, item: card.id, rarity: "common", new: true, ts: 20, source: "craft" },
      { id: 1, item: card.id, rarity: "common", new: true, ts: 10 },
    ]);
    expect(rows.map((r) => [r.id, r.item.id, r.tier, r.fresh, r.from])).toEqual([
      [4, skin.id, "皮肤", true, "双形态"],
      [3, card.id, "普通", false, ""],
      [2, card.id, "普通", true, "兑换"],
      [1, card.id, "普通", true, ""],
    ]);
  });
  it("calls a limited pool the server no longer lists by a plain name", () => {
    const [row] = rowsOf([{ id: 1, item: card.id, rarity: "common", new: true, ts: 1, source: "draw", pool: "gone" }]);
    expect(row.from).toBe("限定卡池");
  });
  it("shows a holo version as its card", () => {
    expect(holoCard).toBeTruthy();
    const [row] = rowsOf([{ id: 1, item: `holo:${holoCard!.id}`, rarity: "common", new: true, ts: 1, source: "draw" }]);
    expect([row.item.id, row.holo]).toEqual([`card:${holoCard!.id}`, true]);
    expect(rowsOf([{ id: 2, item: card.id, rarity: "common", new: true, ts: 1 }])[0].holo).toBe(false);
  });
  it("leaves out what this client's catalog does not know", () => {
    expect(rowsOf([
      { id: 2, item: "card:from-a-later-release", rarity: "rare", new: true, ts: 2 },
      { id: 1, item: card.id, rarity: "common", new: true, ts: 1 },
    ]).map((r) => r.id)).toEqual([1]);
  });
});

describe("days", () => {
  const now = new Date(2026, 10, 18, 9, 30).getTime();
  it("are this machine's, with the time of day beside each drop", () => {
    expect(dayKey(at(2026, 11, 5, 23, 59))).toBe("2026-11-05");
    expect(clockOf(at(2026, 11, 5, 7, 5))).toBe("07:05");
  });
  it("are headed 今日, 昨日, then by date, with the year when it is another one", () => {
    expect(dayLabel("2026-11-18", now)).toBe("今日");
    expect(dayLabel("2026-11-17", now)).toBe("昨日");
    expect(dayLabel("2026-11-05", now)).toBe("11月5日");
    expect(dayLabel("2025-12-31", now)).toBe("2025年12月31日");
    // The day before the first of a month.
    expect(dayLabel("2026-10-31", new Date(2026, 10, 1, 0, 5).getTime())).toBe("昨日");
  });
  it("group the rows in their order", () => {
    const rows = rowsOf([
      { id: 3, item: card.id, rarity: "common", new: true, ts: at(2026, 11, 18, 9) },
      { id: 2, item: card.id, rarity: "common", new: false, ts: at(2026, 11, 18, 1) },
      { id: 1, item: card.id, rarity: "common", new: false, ts: at(2026, 11, 16, 22) },
    ]);
    expect(byDay(rows, now).map((d) => [d.label, d.rows.map((r) => r.id)])).toEqual([["今日", [3, 2]], ["11月16日", [1]]]);
  });
});
