// The pen writing a signature: where its tip is, and how bright the light on it.
import { clamp, lerp } from "./math";
import type { CardModel } from "./painter";

/** Further apart than this, in texels, the pen was lifted and set down somewhere else. */
const LIFT = 90;

export function movePen(c: CardModel, dt: number): void {
  const path = c.info.signed?.tip;
  if (!path) return;
  const f = clamp(c.signT) * (path.length - 1), i = Math.floor(f), from = path[i], to = path[Math.min(path.length - 1, i + 1)];
  const busy = c.signT >= 0 && c.signT < 1.01 && !!from;
  if (busy) {
    const near = to && Math.hypot(to[0] - from[0], to[1] - from[1]) < LIFT;
    c.tip = near ? [lerp(from[0], to[0], f - i), lerp(from[1], to[1], f - i)] : from;
  }
  c.tipAmt += ((busy ? 1 : 0) - c.tipAmt) * (1 - Math.exp(-dt / (busy ? 60 : 160)));
}
