import { PET_BASE } from "../characters";
// Where pets stand on the desktop overlay. Own pet and panel positions live in settings;
// other members' pets are remembered per room (by member key) in localStorage, so a
// friend you dragged next to your pet stays there next time. In formation mode partners stand in rows instead,
// placed by one anchor kept in settings; in row mode they stand side by side on the bottom edge, all in one row, which
// runs off the screen's sides when it is wider.
import { reactive, ref } from "vue";
import { isMirrorWindow } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { settings } from "./settings";

const KEY = "asoultappo.desk.v1";
const MAX_ROOMS = 10;

export interface Pos { x: number; y: number }
export interface Size { w: number; h: number }
/** A partner's place; a docked one stands on the bottom edge at `x`. */
export interface Spot extends Pos { docked?: boolean }

/** Overlay viewport size (CSS px), kept up to date by the app root. */
export const viewport = ref<Size>({ w: 1280, h: 720 });

type Saved = Record<string, Record<string, Spot>>;

function load(): Saved {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return v && typeof v === "object" ? v : {};
  } catch {
    return {};
  }
}

const saved: Saved = load();
/** Positions of other members' pets in the current room. */
export const remotePos = reactive(new Map<string, Spot>());
let currentRoom = "";

function persist(): void {
  const rooms = Object.keys(saved);
  for (const r of rooms.slice(0, Math.max(0, rooms.length - MAX_ROOMS))) delete saved[r];
  try {
    localStorage.setItem(KEY, JSON.stringify(saved));
  } catch {
    /* storage unavailable */
  }
}

export function clamp(p: Pos, size: Size, vp: Size = viewport.value, margin = 8): Pos {
  return {
    x: Math.round(Math.min(Math.max(margin, p.x), Math.max(margin, vp.w - size.w - margin))),
    y: Math.round(Math.min(Math.max(margin, p.y), Math.max(margin, vp.h - size.h - margin))),
  };
}

/** Canvas pixels of empty picture under the desk; a docked pet sinks by this much so the desk stands on the edge. */
export const DESK_GAP = 12;
/** A pet dragged this close to its docked place snaps into it. */
export const DOCK_SNAP = 18;

/** Top of a pet of [scale] docked on the bottom edge. */
export function dockY(scale: number, vp: Size = viewport.value): number {
  return Math.round(vp.h - (PET_BASE.height - DESK_GAP) * scale);
}

/**
 * Where a pet dragged to [p] goes: onto the bottom edge once it is close to it, else anywhere on screen that
 * keeps what hangs under it visible ([full] is its size with the own pet's strip or a partner's name).
 */
export function placePet(p: Pos, full: Size, scale: number, vp: Size = viewport.value): { pos: Pos; docked: boolean } {
  const bottom = dockY(scale, vp);
  if (p.y >= bottom - DOCK_SNAP) return { pos: { x: clamp(p, full, vp).x, y: bottom }, docked: true };
  return { pos: clamp(p, full, vp), docked: false };
}

/** Default place of the own pet: bottom right, leaving room below for the quick emote dock. */
export function defaultPetPos(size: Size, vp: Size = viewport.value): Pos {
  return clamp({ x: vp.w - size.w - 48, y: vp.h - size.h - 80 }, size, vp);
}

/**
 * Sends the own pet back to its default place, for the tray and the settings page. A docked pet leaves the bottom
 * edge first: docked, it keeps only its x, which would clamp to the left edge. Each field reaches the desk as its own
 * patch when this runs in the panel, so the edge goes first.
 */
export function resetOwnPet(): void {
  settings.petDocked = false;
  settings.petX = -1;
  settings.petY = -1;
}

/**
 * Free slots next to the own pet for newcomers: first a row to its left, then rows above.
 * `taken` are rectangles already in use (top-left positions with `size`).
 */
export function nextSlot(own: Pos, ownSize: Size, size: Size, taken: Pos[], vp: Size = viewport.value): Pos {
  const gap = 16;
  const overlaps = (p: Pos) =>
    taken.some((t) => Math.abs(t.x - p.x) < size.w + gap / 2 && Math.abs(t.y - p.y) < size.h + gap / 2) ||
    (p.x < own.x + ownSize.w && p.x + size.w > own.x && p.y < own.y + ownSize.h && p.y + size.h > own.y);
  const baseY = own.y + ownSize.h - size.h;
  for (let row = 0; row < 8; row++) {
    const y = baseY - row * (size.h + gap);
    for (let col = 1; col < 12; col++) {
      for (const dir of [-1, 1]) {
        const x = dir < 0 ? own.x - col * (size.w + gap) : own.x + ownSize.w + gap + (col - 1) * (size.w + gap);
        const p = { x, y };
        const c = clamp(p, size, vp);
        if (c.x === Math.round(p.x) && c.y === Math.round(p.y) && !overlaps(c)) return c;
      }
    }
  }
  return clamp({ x: own.x - size.w - gap, y: baseY }, size, vp);
}

/**
 * A free place on the bottom edge next to the docked own pet, first to its left; null when the edge is full.
 * Only docked partners in `taken` count, the others stand higher up.
 */
export function nextDockSlot(own: Pos, ownSize: Size, size: Size, taken: Spot[], vp: Size = viewport.value): Spot | null {
  const gap = 16;
  const margin = 8;
  const free = (x: number) =>
    x >= margin && x + size.w <= vp.w - margin &&
    !(x < own.x + ownSize.w && x + size.w > own.x) &&
    !taken.some((t) => t.docked && Math.abs(t.x - x) < size.w + gap / 2);
  for (let col = 1; col < 12; col++) {
    for (const dir of [-1, 1]) {
      const x = Math.round(dir < 0 ? own.x - col * (size.w + gap) : own.x + ownSize.w + gap + (col - 1) * (size.w + gap));
      if (free(x)) return { x, y: 0, docked: true };
    }
  }
  return null;
}

// ---- formation: partners in rows of `cols`, filled left to right, top to bottom, moved as one.

/** Space between formation cells, as between the slots next to the own pet. */
export const FORMATION_GAP = 16;
/** A formation's top-left and whether its last row stands on the bottom edge. */
export interface FormationPlace { anchor: Pos; docked: boolean }

const formationGrid = (n: number, cols: number) => {
  const c = Math.max(1, Math.min(Math.round(cols), n));
  return { cols: c, rows: n > 0 ? Math.ceil(n / c) : 0 };
};

/** Size of a formation of [n] pets of [size]; empty for none. */
export function formationSize(n: number, cols: number, size: Size, gap = FORMATION_GAP): Size {
  const g = formationGrid(n, cols);
  if (!g.rows) return { w: 0, h: 0 };
  return { w: g.cols * size.w + (g.cols - 1) * gap, h: g.rows * size.h + (g.rows - 1) * gap };
}

/** Where the [i]th pet stands relative to the formation's top-left. */
export function formationOffset(i: number, cols: number, size: Size, gap = FORMATION_GAP): Pos {
  const c = Math.max(1, Math.round(cols));
  return { x: (i % c) * (size.w + gap), y: Math.floor(i / c) * (size.h + gap) };
}

/** Whether the [i]th of [n] pets is in the last row. */
export function inLastRow(i: number, n: number, cols: number): boolean {
  const g = formationGrid(n, cols);
  return g.rows > 0 && Math.floor(i / g.cols) === g.rows - 1;
}

/** Top-left of each of [n] pets placed at [anchor]. */
export function formationCells(anchor: Pos, n: number, cols: number, size: Size, gap = FORMATION_GAP): Pos[] {
  const c = formationGrid(n, cols).cols;
  return Array.from({ length: n }, (_, i) => {
    const o = formationOffset(i, c, size, gap);
    return { x: anchor.x + o.x, y: anchor.y + o.y };
  });
}

/**
 * Left edge of something [w] px wide at [x]: kept on screen while it fits; wider than the screen, it moves sideways
 * until either of its ends is on screen.
 */
export function panX(x: number, w: number, vp: Size = viewport.value, margin = 8): number {
  const far = vp.w - margin - w;
  return Math.round(Math.min(Math.max(x, Math.min(margin, far)), Math.max(margin, far)));
}

/**
 * Where a formation goes: a docked one keeps its last row on the bottom edge (pets of [scale], as dockY) and only its
 * x is kept on screen; any other is kept fully on screen. [docked] unset decides it as placePet does for one pet:
 * docked once the last row comes within DOCK_SNAP of its docked place. With [pan] (row mode) a docked one wider than
 * the screen may stand anywhere panX allows.
 */
export function placeFormation(
  p: Pos, n: number, cols: number, size: Size, scale: number, vp: Size = viewport.value, docked?: boolean, pan = false,
): FormationPlace {
  const full = formationSize(n, cols, size);
  if (!full.h) return { anchor: clamp(p, size, vp), docked: !!docked };
  const lastRow = full.h - size.h;
  const bottom = dockY(scale, vp);
  const dock = docked ?? p.y + lastRow >= bottom - DOCK_SNAP;
  if (dock) return { anchor: { x: pan ? panX(p.x, full.w, vp) : clamp(p, full, vp).x, y: bottom - lastRow }, docked: true };
  return { anchor: clamp(p, full, vp), docked: false };
}

/**
 * The formation's place before it is dragged: bottom-aligned with the own pet and to its left, on the right when the
 * left has no room, clamped when neither has. Next to a docked own pet the formation docks too.
 */
export function defaultFormation(
  own: Pos, ownSize: Size, ownDocked: boolean, n: number, cols: number, size: Size, scale: number,
  vp: Size = viewport.value, pan = false,
): FormationPlace {
  const full = formationSize(n, cols, size);
  const margin = 8;
  let x = own.x - FORMATION_GAP - full.w;
  const right = own.x + ownSize.w + FORMATION_GAP;
  if (x < margin && right + full.w <= vp.w - margin) x = right;
  return placeFormation({ x, y: own.y + ownSize.h - full.h }, n, cols, size, scale, vp, ownDocked, pan);
}

export function enterRoom(room: string): void {
  currentRoom = room;
  remotePos.clear();
  for (const [k, p] of Object.entries(saved[room] ?? {})) remotePos.set(k, p);
}

export function placeRemote(key: string, p: Spot): void {
  remotePos.set(key, p);
  if (!currentRoom) return;
  delete saved[currentRoom]; // re-insert: most recently used rooms are kept
  saved[currentRoom] = Object.fromEntries(remotePos);
  persist();
}

/**
 * Forget remembered positions in this room so everyone lines up next to the own pet again. In formation or row mode
 * that goes back next to the own pet instead; free positions are kept for switching back.
 */
export function tidyRemotes(): void {
  if (settings.partnerLayout === "formation") {
    settings.formationX = settings.formationY = -1;
    settings.formationDocked = false;
    return;
  }
  if (settings.partnerLayout === "row") {
    settings.partnerRowX = -1;
    return;
  }
  if (isMirrorWindow) { void requestDesktop("tidyRemotes"); return; }
  remotePos.clear();
  if (currentRoom) {
    delete saved[currentRoom];
    persist();
  }
}
