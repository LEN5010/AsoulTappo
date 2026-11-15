// Album browsing: stepping through what a grid shows, and the zoom of the full-panel viewer.

/**
 * Index of the nearest item before (`delta` -1) or after (`delta` 1) the item with `currentId` that passes
 * `can`, or -1 at either end. The current item itself may fail `can` (an unowned card opened from the grid).
 */
export function stepIndex<T>(
  list: readonly T[], currentId: string, idOf: (item: T) => string, delta: 1 | -1, can: (item: T) => boolean,
): number {
  const at = list.findIndex((item) => idOf(item) === currentId);
  if (at < 0) return -1;
  for (let i = at + delta; i >= 0 && i < list.length; i += delta) {
    if (can(list[i]!)) return i;
  }
  return -1;
}

export interface Size { w: number; h: number }
/** Scale of the art and its offset; the frame scales from its top left corner. */
export interface View { scale: number; x: number; y: number }

export const MIN_SCALE = 1;
export const MAX_SCALE = 3;
export const FIT: View = { scale: 1, x: 0, y: 0 };

export const clampScale = (scale: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

/** The largest box of `ratio` (width / height) inside `box`. */
export function fitSize(ratio: number, box: Size): Size {
  if (!(ratio > 0) || box.w <= 0 || box.h <= 0) return { w: 0, h: 0 };
  const w = Math.min(box.w, box.h * ratio);
  return { w, h: w / ratio };
}

/**
 * Keeps the scaled art over the box: centred on an axis where it is smaller than the box, and with no
 * gap at either edge where it is larger. `size` is the art at scale 1, centred in `box`.
 */
export function clampPan(view: View, size: Size, box: Size): View {
  const axis = (offset: number, length: number, room: number) => {
    // Offset that centres the scaled art in the box, as the frame grows from its top left corner.
    const centre = (length - length * view.scale) / 2;
    const slack = Math.max(0, (length * view.scale - room) / 2);
    return Math.min(centre + slack, Math.max(centre - slack, offset));
  };
  return { scale: view.scale, x: axis(view.x, size.w, box.w), y: axis(view.y, size.h, box.h) };
}

/** Zooms to `scale` and keeps the point `at` (relative to the art's top left at scale 1) where it is on screen. */
export function zoomAt(view: View, scale: number, at: { x: number; y: number }, size: Size, box: Size): View {
  const next = clampScale(scale);
  const k = next / view.scale;
  return clampPan({ scale: next, x: at.x - (at.x - view.x) * k, y: at.y - (at.y - view.y) * k }, size, box);
}
