import { describe, expect, it } from "vitest";
import { moved, nearestSlot, slotWhileDragging } from "./showcaseDrag";

describe("dragging a showcase card", () => {
  const centers = [100, 186, 272, 358];
  it("aims at the slot nearest to the card's centre, ends included", () => {
    expect(nearestSlot(centers, 90)).toBe(0);
    expect(nearestSlot(centers, 230)).toBe(2);
    expect(nearestSlot(centers, 900)).toBe(3);
    expect(nearestSlot(centers, -50)).toBe(0);
  });
  it("moves the cards between one slot toward where the dragged card came from", () => {
    // From 0 to 2: cards 1 and 2 move left, 3 stays.
    expect([0, 1, 2, 3].map((i) => slotWhileDragging(i, 0, 2))).toEqual([0, 0, 1, 3]);
    // From 3 to 1: cards 1 and 2 move right, 0 stays.
    expect([0, 1, 2, 3].map((i) => slotWhileDragging(i, 3, 1))).toEqual([0, 2, 3, 3]);
    expect([0, 1, 2, 3].map((i) => slotWhileDragging(i, 2, 2))).toEqual([0, 1, 2, 3]);
  });
  it("hands up the order with the card in its new place", () => {
    expect(moved(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
    expect(moved(["a", "b", "c", "d"], 3, 1)).toEqual(["a", "d", "b", "c"]);
    expect(moved(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });
});
