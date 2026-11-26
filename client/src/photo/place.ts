// Where a thing stands on the screen, for another view to take it over.
import type { BoxModel } from "./painter";

/** A box: the point its perspective is drawn toward in client pixels, CSS pixels to a design unit, and the box in design
 *  units from that point. */
export interface BoxPlace { cx: number; cy: number; css: number; box: BoxModel }
/** A card: its middle in client pixels, its size upright, and how far it is turned, in degrees. */
export interface CardPlace { x: number; y: number; w: number; h: number; rz: number }

export function placeOf(el: Element): CardPlace {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, rz: 0 };
}
