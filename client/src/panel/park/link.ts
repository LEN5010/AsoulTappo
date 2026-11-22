// The park link game's board rules (连连看, Shisen-Sho rules; docs/design/park-link.md section 3), for drawing lines,
// hints and spotting a stuck board. server/app/link.py holds the same rules and decides; both are checked against
// link.fixture.json (server/tests/gen_link_fixture.py). Boards are generated and shuffled on the server only.
//
// A board is a flat array of rows * cols kinds, index r * cols + c, with EMPTY for a removed tile. Two tiles of one
// kind link when a line of at most three horizontal and vertical segments (two turns) joins them over empty cells;
// the ring just outside the board (row -1 and rows, column -1 and cols) is always empty.
//
// Path search follows KDE KShisen src/board.cpp (findPath, findSimplePath; GPL-2.0-or-later), with candidates
// enumerated in a fixed order so the line drawn is the one the server's rules give.

export const EMPTY = -1;

export type Shift = "none" | "down" | "left" | "center";

/** A corner of a line as [row, column]; ring cells have row -1 or rows, or column -1 or cols. */
export type Point = [number, number];

function free(board: readonly number[], rows: number, cols: number, r: number, c: number): boolean {
  return r < 0 || r >= rows || c < 0 || c >= cols || board[r * cols + c] === EMPTY;
}

/** Every cell of row r strictly between columns c1 and c2 is empty. */
function rowClear(board: readonly number[], rows: number, cols: number, r: number, c1: number, c2: number): boolean {
  if (r < 0 || r >= rows) return true;
  const lo = Math.min(c1, c2);
  const hi = Math.max(c1, c2);
  for (let c = Math.max(lo + 1, 0); c < Math.min(hi, cols); c++) {
    if (board[r * cols + c] !== EMPTY) return false;
  }
  return true;
}

/** Every cell of column c strictly between rows r1 and r2 is empty. */
function colClear(board: readonly number[], rows: number, cols: number, c: number, r1: number, r2: number): boolean {
  if (c < 0 || c >= cols) return true;
  const lo = Math.min(r1, r2);
  const hi = Math.max(r1, r2);
  for (let r = Math.max(lo + 1, 0); r < Math.min(hi, rows); r++) {
    if (board[r * cols + c] !== EMPTY) return false;
  }
  return true;
}

/** The line between cells a and b, whatever they hold, or null. Candidates in order: the straight line; one turn at
 * (ra, cb), then at (rb, ca); two turns through each row R from -1 to rows (vertically to row R, along it, vertically
 * to b), then through each column C from -1 to cols. With `best` the line with the fewest turns, then the shortest
 * total length, wins, the first in this order on a tie; without it, the first line found. */
function route(board: readonly number[], rows: number, cols: number, a: number, b: number, best: boolean): Point[] | null {
  const r1 = Math.floor(a / cols);
  const c1 = a % cols;
  const r2 = Math.floor(b / cols);
  const c2 = b % cols;
  if (r1 === r2 && rowClear(board, rows, cols, r1, c1, c2)) return [[r1, c1], [r2, c2]];
  if (c1 === c2 && colClear(board, rows, cols, c1, r1, r2)) return [[r1, c1], [r2, c2]];
  if (r1 !== r2 && c1 !== c2) {
    if (free(board, rows, cols, r1, c2) && rowClear(board, rows, cols, r1, c1, c2)
      && colClear(board, rows, cols, c2, r1, r2)) return [[r1, c1], [r1, c2], [r2, c2]];
    if (free(board, rows, cols, r2, c1) && colClear(board, rows, cols, c1, r1, r2)
      && rowClear(board, rows, cols, r2, c1, c2)) return [[r1, c1], [r2, c1], [r2, c2]];
  }
  let found: Point[] | null = null;
  let length = 0;
  if (c1 !== c2) {
    // The run of empty cells above and below each end bounds the rows a line can turn in.
    let lo1 = r1, hi1 = r1, lo2 = r2, hi2 = r2;
    while (lo1 > -1 && free(board, rows, cols, lo1 - 1, c1)) lo1--;
    while (hi1 < rows && free(board, rows, cols, hi1 + 1, c1)) hi1++;
    while (lo2 > -1 && free(board, rows, cols, lo2 - 1, c2)) lo2--;
    while (hi2 < rows && free(board, rows, cols, hi2 + 1, c2)) hi2++;
    for (let r = Math.max(lo1, lo2); r <= Math.min(hi1, hi2); r++) {
      if (r === r1 || r === r2 || !rowClear(board, rows, cols, r, c1, c2)) continue;
      const n = Math.abs(r - r1) + Math.abs(c1 - c2) + Math.abs(r - r2);
      if (found === null || n < length) {
        found = [[r1, c1], [r, c1], [r, c2], [r2, c2]];
        length = n;
        if (!best) return found;
      }
    }
  }
  if (r1 !== r2) {
    let lo1 = c1, hi1 = c1, lo2 = c2, hi2 = c2;
    while (lo1 > -1 && free(board, rows, cols, r1, lo1 - 1)) lo1--;
    while (hi1 < cols && free(board, rows, cols, r1, hi1 + 1)) hi1++;
    while (lo2 > -1 && free(board, rows, cols, r2, lo2 - 1)) lo2--;
    while (hi2 < cols && free(board, rows, cols, r2, hi2 + 1)) hi2++;
    for (let c = Math.max(lo1, lo2); c <= Math.min(hi1, hi2); c++) {
      if (c === c1 || c === c2 || !colClear(board, rows, cols, c, r1, r2)) continue;
      const n = Math.abs(c - c1) + Math.abs(r1 - r2) + Math.abs(c - c2);
      if (found === null || n < length) {
        found = [[r1, c1], [r1, c], [r2, c], [r2, c2]];
        length = n;
        if (!best) return found;
      }
    }
  }
  return found;
}

function pairOk(board: readonly number[], a: number, b: number): boolean {
  const n = board.length;
  return Number.isInteger(a) && Number.isInteger(b) && a !== b && a >= 0 && a < n && b >= 0 && b < n
    && board[a] !== EMPTY && board[a] === board[b];
}

/** The corners of the line joining tiles a and b, both ends included; null when they are the same cell, either is
 * empty, the kinds differ or no line of at most two turns exists. The line has the fewest turns, then the shortest
 * length (see route for the order that breaks ties). */
export function connect(board: readonly number[], rows: number, cols: number, a: number, b: number): Point[] | null {
  if (!pairOk(board, a, b)) return null;
  return route(board, rows, cols, a, b, true);
}

/** A new board with the tiles moved by `shift`, each line keeping its order: none leaves them, down drops each column
 * to the bottom, left packs each row to the left, center packs each half row toward the middle line (the left half,
 * c < cols / 2, to its right end; the right half to its left end). The input is not changed. */
export function applyShift(board: readonly number[], rows: number, cols: number, shift: Shift): number[] {
  const out = board.slice();
  if (shift === "down") {
    for (let c = 0; c < cols; c++) {
      const tiles: number[] = [];
      for (let r = 0; r < rows; r++) if (board[r * cols + c] !== EMPTY) tiles.push(board[r * cols + c]);
      const pad = rows - tiles.length;
      for (let r = 0; r < rows; r++) out[r * cols + c] = r < pad ? EMPTY : tiles[r - pad];
    }
  } else if (shift === "left") {
    for (let r = 0; r < rows; r++) {
      const tiles = board.slice(r * cols, (r + 1) * cols).filter((t) => t !== EMPTY);
      for (let c = 0; c < cols; c++) out[r * cols + c] = c < tiles.length ? tiles[c] : EMPTY;
    }
  } else if (shift === "center") {
    const half = cols >> 1;
    for (let r = 0; r < rows; r++) {
      const left = board.slice(r * cols, r * cols + half).filter((t) => t !== EMPTY);
      const right = board.slice(r * cols + half, (r + 1) * cols).filter((t) => t !== EMPTY);
      const pad = half - left.length;
      for (let c = 0; c < half; c++) out[r * cols + c] = c < pad ? EMPTY : left[c - pad];
      for (let c = 0; c < cols - half; c++) out[r * cols + half + c] = c < right.length ? right[c] : EMPTY;
    }
  }
  return out;
}

/** A new board with cells a and b emptied, then shifted. It does not check the pair; the input is not changed. */
export function removePair(board: readonly number[], rows: number, cols: number, shift: Shift, a: number, b: number): number[] {
  const out = board.slice();
  out[a] = EMPTY;
  out[b] = EMPTY;
  return applyShift(out, rows, cols, shift);
}

/** The first pair of tiles that link, scanning a from the smallest index and b from a + 1 up; null if none do. */
export function findPair(board: readonly number[], rows: number, cols: number): [number, number] | null {
  for (let a = 0; a < board.length; a++) {
    if (board[a] === EMPTY) continue;
    for (let b = a + 1; b < board.length; b++) {
      if (board[b] === board[a] && route(board, rows, cols, a, b, false) !== null) return [a, b];
    }
  }
  return null;
}
