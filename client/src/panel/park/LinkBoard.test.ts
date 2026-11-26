import { createSSRApp, h } from "vue";
import { renderToString } from "vue/server-renderer";
import { describe, expect, it } from "vitest";
import LinkBoard, { nearestCell, stepCell } from "./LinkBoard.vue";

// 3×4, cells by index:
//  0  1  2  3
//  4  5  6  7
//  8  9 10 11
describe("link board keys", () => {
  const all = [...Array(12).keys()];

  it("steps to the next tile each way, over the empty cells", () => {
    expect(stepCell(all, 4, 5, "ArrowRight")).toBe(6);
    expect(stepCell(all, 4, 5, "ArrowLeft")).toBe(4);
    expect(stepCell(all, 4, 5, "ArrowUp")).toBe(1);
    expect(stepCell(all, 4, 5, "ArrowDown")).toBe(9);
    expect(stepCell([5, 7], 4, 5, "ArrowRight")).toBe(7);
    expect(stepCell([1, 9], 4, 1, "ArrowDown")).toBe(9);
  });

  it("keeps to the row or column first, then the nearest one off it", () => {
    expect(stepCell([4, 3, 7], 4, 4, "ArrowRight")).toBe(7);
    expect(stepCell([4, 2, 11], 4, 4, "ArrowRight")).toBe(2);
    expect(stepCell([4, 10, 3], 4, 4, "ArrowRight")).toBe(10);
  });

  it("stays put at the edge and for other keys", () => {
    expect(stepCell(all, 4, 7, "ArrowRight")).toBeNull();
    expect(stepCell(all, 4, 0, "ArrowUp")).toBeNull();
    expect(stepCell(all, 4, 5, "Enter")).toBeNull();
    expect(stepCell(all, 4, 5, "a")).toBeNull();
  });

  it("finds the tile nearest to a cell that has gone", () => {
    expect(nearestCell([0, 11], 4, 5)).toBe(0);
    expect(nearestCell([3, 8, 10], 4, 6)).toBe(10);
    expect(nearestCell([], 4, 6)).toBeNull();
  });
});

describe("link board tab order", () => {
  const board = [0, 0, 1, 1, 1, 1, 0, -1];
  const tiles = [1, 2, 3, 4, 5, 6, 7, -1];
  const render = (selected: number | null) =>
    renderToString(createSSRApp({
      render: () => h(LinkBoard, {
        rows: 2, cols: 4, board, tiles, faces: ["a.webp", "b.webp"], names: ["a", "b"], selected, minPitch: 32, hint: [],
        lines: [], ghosts: [], shake: null, deal: 1, flip: 0, dim: false, disabled: false, calm: true,
      }),
    }));
  const stops = (html: string) => [...html.matchAll(/<button[^>]*tabindex="0"[^>]*data-at="(\d+)"/g)].map((m) => Number(m[1]));

  it("puts one tile in the tab order: the first one, or the one picked", async () => {
    let html = await render(null);
    expect(html.match(/tabindex="0"/g)).toHaveLength(1);
    expect(html.match(/tabindex="-1"/g)).toHaveLength(6);
    expect(stops(html)).toEqual([0]);
    html = await render(5);
    expect(html.match(/tabindex="0"/g)).toHaveLength(1);
    expect(stops(html)).toEqual([4]);
  });
});
