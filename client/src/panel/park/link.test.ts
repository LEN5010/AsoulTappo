import { describe, expect, it } from "vitest";
import { applyShift, connect, EMPTY, findPair, removePair, type Point, type Shift } from "./link";
import raw from "./link.fixture.json";

// Written by server/tests/gen_link_fixture.py from server/app/link.py, which decides.
interface Fixture {
  connect: { name: string; rows: number; cols: number; board: number[]; a: number; b: number; path: Point[] | null }[];
  boards: { rows: number; cols: number; board: number[]; pairs: { a: number; b: number; path: Point[] | null }[] }[];
  shift: { rows: number; cols: number; board: number[]; shift: Shift; out: number[] }[];
  find: { rows: number; cols: number; board: number[]; pair: [number, number] | null }[];
  sequences: { rows: number; cols: number; shift: Shift; board: number[]; steps: { a: number; b: number; board: number[] }[] }[];
}
const fixture = raw as unknown as Fixture;

describe("link rules match the server", () => {
  it("draws the same line for every fixture pair", () => {
    for (const c of fixture.connect) {
      expect(connect(c.board, c.rows, c.cols, c.a, c.b), c.name).toEqual(c.path);
    }
    for (const d of fixture.boards) {
      for (const p of d.pairs) expect(connect(d.board, d.rows, d.cols, p.a, p.b), `${p.a}-${p.b}`).toEqual(p.path);
    }
  });

  it("shifts boards as the server does", () => {
    for (const s of fixture.shift) {
      expect(applyShift(s.board, s.rows, s.cols, s.shift), s.shift).toEqual(s.out);
    }
  });

  it("finds the same first pair", () => {
    for (const f of fixture.find) expect(findPair(f.board, f.rows, f.cols)).toEqual(f.pair);
  });

  it("replays greedy play step by step under each shift", () => {
    for (const q of fixture.sequences) {
      let board = q.board;
      for (const step of q.steps) {
        expect(findPair(board, q.rows, q.cols)).toEqual([step.a, step.b]);
        expect(connect(board, q.rows, q.cols, step.a, step.b)).not.toBeNull();
        board = removePair(board, q.rows, q.cols, q.shift, step.a, step.b);
        expect(board).toEqual(step.board);
      }
      expect(findPair(board, q.rows, q.cols)).toBeNull();
    }
  });
});

describe("link rules", () => {
  it("leaves the input board alone", () => {
    const board = [0, EMPTY, 1, 1, EMPTY, 0, 2, 2];
    const copy = board.slice();
    for (const s of ["none", "down", "left", "center"] as Shift[]) removePair(board, 2, 4, s, 0, 5);
    expect(board).toEqual(copy);
  });

  it("refuses the same cell, empty cells and different kinds", () => {
    const board = [0, 0, EMPTY, 1];
    expect(connect(board, 1, 4, 0, 0)).toBeNull();
    expect(connect(board, 1, 4, 0, 2)).toBeNull();
    expect(connect(board, 1, 4, 0, 3)).toBeNull();
    expect(connect(board, 1, 4, 0, 1)).toEqual([[0, 0], [0, 1]]);
    expect(connect([0, 0, 0, 0], 1, 4, 0.25, 0.75)).toBeNull();
    expect(connect([0, 0, 0, 0], 1, 4, 0, 1.5)).toBeNull();
  });
});
