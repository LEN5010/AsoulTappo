// Where pets stand on the desktop overlay. Own pet and panel positions live in settings;
// other members' pets are remembered per room (by member key) in localStorage, so a
// friend you dragged next to your pet stays there next time.
import { reactive, ref } from "vue";
import { isPanelWindow } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";

const KEY = "asoultappo.desk.v1";
const MAX_ROOMS = 10;

export interface Pos { x: number; y: number }
export interface Size { w: number; h: number }

/** Overlay viewport size (CSS px), kept up to date by the app root. */
export const viewport = ref<Size>({ w: 1280, h: 720 });

type Saved = Record<string, Record<string, Pos>>;

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
export const remotePos = reactive(new Map<string, Pos>());
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

/** Default place of the own pet: bottom right, leaving room below for the quick emote dock. */
export function defaultPetPos(size: Size, vp: Size = viewport.value): Pos {
  return clamp({ x: vp.w - size.w - 48, y: vp.h - size.h - 80 }, size, vp);
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

export function enterRoom(room: string): void {
  currentRoom = room;
  remotePos.clear();
  for (const [k, p] of Object.entries(saved[room] ?? {})) remotePos.set(k, p);
}

export function placeRemote(key: string, p: Pos): void {
  remotePos.set(key, p);
  if (!currentRoom) return;
  delete saved[currentRoom]; // re-insert: most recently used rooms are kept
  saved[currentRoom] = Object.fromEntries(remotePos);
  persist();
}

/** Forget remembered positions in this room so everyone lines up next to the own pet again. */
export function tidyRemotes(): void {
  if (isPanelWindow) { void requestDesktop("tidyRemotes"); return; }
  remotePos.clear();
  if (currentRoom) {
    delete saved[currentRoom];
    persist();
  }
}
