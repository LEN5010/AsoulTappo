import { expect, it } from "vitest";
import { newsLine, rememberNews, unseenNews } from "./parkNews";
import type { ParkNews } from "./net/api";
import { manifest } from "./manifest";

const item = (id: number, kind = "jackpot", extra: Record<string, unknown> = {}): ParkNews =>
  ({ id, ts: 1000 + id, kind, nick: `n${id}`, ...extra });

it("lists the news not seen yet, oldest first", () => {
  const news = [item(9), item(7), item(8)];
  expect(unseenNews(news, new Set([8])).map((n) => n.id)).toEqual([7, 9]);
  expect(unseenNews(undefined, new Set())).toEqual([]);
  expect(unseenNews(news, new Set([7, 8, 9]))).toEqual([]);
});

it("remembers seen ids without repeats, keeping the newest", () => {
  expect(rememberNews([3, 1], [2, 3])).toEqual([1, 2, 3]);
  expect(rememberNews([1, 2, 3], [4, 5], 3)).toEqual([3, 4, 5]);
});

it("says what was won, and skips kinds it does not know", () => {
  expect(newsLine(item(1, "jackpot", { shards: 213400 }))).toEqual({ nick: "n1", text: "刮中全服奖池", shards: 213400 });
  expect(newsLine(item(2, "scratch_big", { shards: 50000 }))?.shards).toBe(50000);
  const skin = manifest.skins[0]!;
  expect(newsLine(item(3, "scratch_item", { item: `char:${skin.name}` }))?.text).toBe(`刮出${skin.title ?? skin.name}`);
  expect(newsLine(item(4, "scratch_item", { item: "card:nope" }))?.text).toBe("刮出大隐藏卡");
  expect(newsLine(item(5, "lottery_draw", { number: 7, nick: "" }))).toEqual({ nick: "", text: "每日夺宝开奖 007", shards: null });
  expect(newsLine(item(6, "something_new"))).toBeNull();
  expect(newsLine({ id: 7, ts: 0, kind: "jackpot" } as unknown as ParkNews)).toEqual({ nick: "", text: "刮中全服奖池", shards: null });
});
