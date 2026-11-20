import { describe, expect, it } from "vitest";
import { rank } from "./rules";
import { arrange, cardAt, fan, pickJokers, pickRank, rankOfKey, stampOf } from "./table";

describe("ddz table", () => {
  it("fans a hand into the room it has", () => {
    expect(fan(0, 500, 64, 38)).toEqual({ step: 0, width: 0 });
    expect(fan(1, 500, 64, 38)).toEqual({ step: 0, width: 64 });
    expect(fan(5, 500, 64, 38)).toEqual({ step: 38, width: 216 });
    const tight = fan(20, 500, 64, 38);
    expect(tight.width).toBeCloseTo(500);
    expect(tight.step).toBeCloseTo(436 / 19);
    expect(fan(20, 100, 64, 38).step).toBe(6); // never closer than this
  });

  it("finds the card under the pointer", () => {
    expect(cardAt(-1, 5, 30, 64)).toBe(-1);
    expect(cardAt(0, 5, 30, 64)).toBe(0);
    expect(cardAt(29, 5, 30, 64)).toBe(0);
    expect(cardAt(30, 5, 30, 64)).toBe(1);
    expect(cardAt(150, 5, 30, 64)).toBe(4); // the last card shows whole
    expect(cardAt(184, 5, 30, 64)).toBe(4);
    expect(cardAt(185, 5, 30, 64)).toBe(-1);
    expect(cardAt(10, 0, 30, 64)).toBe(-1);
    expect(cardAt(10, 1, 0, 64)).toBe(0);
  });

  it("picks cards by rank key", () => {
    const hand = [53, 52, 21, 20, 4, 0]; // jokers, 8 8, 4, 3
    expect(rankOfKey("8")).toBe(8);
    expect(rankOfKey("0")).toBe(10);
    expect(["J", "q", "K", "a", "2"].map(rankOfKey)).toEqual([11, 12, 13, 14, 15]);
    expect(["1", "w", "Tab", " "].map(rankOfKey)).toEqual([null, null, null, null]);
    let sel = pickRank(hand, new Set(), 8);
    expect([...sel]).toEqual([21]);
    sel = pickRank(hand, sel, 8);
    expect([...sel].sort()).toEqual([20, 21]);
    sel = pickRank(hand, sel, 8);
    expect(sel.size).toBe(0);
    expect(pickRank(hand, new Set([4]), 9).size).toBe(1); // none held: nothing changes
    sel = pickJokers(hand, new Set([0]));
    expect([...sel].sort()).toEqual([0, 52]);
    sel = pickJokers(hand, sel);
    sel = pickJokers(hand, sel);
    expect([...sel]).toEqual([0]);
    expect([...pickJokers([53, 0], new Set())]).toEqual([53]);
  });

  it("lays a play out with its main cards first", () => {
    const plane = [0, 1, 2, 4, 5, 6, 44, 48]; // 3 3 3 4 4 4 with A and 2
    expect(arrange(plane).map(rank)).toEqual([4, 4, 4, 3, 3, 3, 15, 14]);
    expect(arrange([0, 4, 8, 12, 16]).map(rank)).toEqual([7, 6, 5, 4, 3]);
    expect(arrange([20, 53, 21, 22, 23, 52]).map(rank)).toEqual([8, 8, 8, 8, 17, 16]);
  });

  it("stamps the long plays and the bombs", () => {
    expect(stampOf([52, 53])).toBe("王炸");
    expect(stampOf([20, 21, 22, 23])).toBe("炸弹");
    expect(stampOf([0, 4, 8, 12, 16])).toBe("顺子");
    expect(stampOf([0, 1, 4, 5, 8, 9])).toBe("连对");
    expect(stampOf([0, 1, 2, 4, 5, 6])).toBe("飞机");
    expect(stampOf([0, 1, 2, 4, 5, 6, 44, 48])).toBe("飞机"); // with wings
    expect(stampOf([0, 1, 2, 4, 5, 6, 40, 41, 44, 45])).toBe("飞机"); // with pairs
    expect(stampOf([0])).toBeNull();
    expect(stampOf([0, 1])).toBeNull();
    expect(stampOf([0, 1, 2, 4])).toBeNull(); // a trio with one
    expect(stampOf([20, 21, 22, 23, 0, 4])).toBeNull(); // four with two
    expect(stampOf([])).toBeNull();
  });
});
