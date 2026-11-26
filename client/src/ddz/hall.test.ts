import { expect, it } from "vitest";
import type { DdzHallTable, DdzLobby } from "../net/protocol";
import { hallOn, hallPreview, hallSeated, hallTables } from "./hall";

const A = { nick: "贝", character: "贝拉" };
const B = { nick: "琳", character: "乃琳" };
const ME = { nick: "我", character: "嘉然" };
const table = (id: string, seats: DdzHallTable["seats"]): DdzHallTable => ({ table: id, seats });
const lobby = (tiers: DdzLobby["tiers"]): DdzLobby =>
  ({ tiers, net: 0, cap: 0, left: 0, taps: 0, minTaps: 0, account: true, seated: false });
const tier = (base: number, waiting: number, tables?: DdzHallTable[]) =>
  ({ base, deposit: base * 48, afford: true, waiting, ...(tables ? { tables } : {}) });

it("knows the hall by the tables its lobby lists, an empty list included", () => {
  expect(hallOn(null)).toBe(false);
  expect(hallOn(lobby([tier(50, 2), tier(250, 0)]))).toBe(false);
  expect(hallOn(lobby([tier(50, 2, []), tier(250, 0, [])]))).toBe(true);
});

it("lists up to three tables of a stake with an empty seat, the own one left out", () => {
  const tables = [
    table("t1", [A, B, null]), table("own", [ME, null, null]), table("t2", [A, { pending: true }, null]),
    table("t3", [A, null, null]), table("t4", [B, null, null]), table("full", [A, B, ME]),
  ];
  const l = lobby([tier(50, 0, tables), tier(250, 0, [table("x", [A, null, null])])]);
  expect(hallTables(l, 50, "own").map((t) => t.table)).toEqual(["t1", "t2", "t3"]);
  expect(hallTables(l, 50, undefined, 9).map((t) => t.table)).toEqual(["t1", "own", "t2", "t3", "t4"]);
  expect(hallTables(l, 500)).toEqual([]);
});

it("counts who sits at a stake's tables, not seats offered to the queue nor the save itself", () => {
  const l = lobby([tier(50, 3, [table("t1", [A, B, null]), table("own", [ME, A, null]), table("t2", [A, { pending: true }, null])])]);
  expect(hallSeated(l, 50)).toBe(5);
  expect(hallSeated(l, 50, "own")).toBe(4);
  expect(hallSeated(l, 250)).toBe(0);
});

it("shows the save in the first empty seat of the table it goes to, or in the middle of a table of its own", () => {
  expect(hallPreview(undefined, ME)).toEqual([null, ME, null]);
  expect(hallPreview(table("t", [{ pending: true }, null, null]), ME)).toEqual(["pending", ME, null]);
  expect(hallPreview(table("t", [A, null, B]), ME, (s) => ({ ...s, nick: `*${s.nick}` }))).toEqual([{ ...A, nick: "*贝" }, ME, { ...B, nick: "*琳" }]);
});
