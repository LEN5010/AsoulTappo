import { PET_BASE } from "../characters";
import { nameBand, plateSize } from "./plates";

/** Match the flex actor's actual children; names never grow wider than the pet. */
export function remotePetSize(scale: number, showNames: boolean, showPlates: boolean) {
  const plate = plateSize(scale);
  return {
    w: Math.max(PET_BASE.width * scale, 64),
    h: PET_BASE.height * scale + (showNames ? Math.max(nameBand(scale).pill, showPlates ? plate.height + 1 : 0) : 0),
  };
}

/** The width the strip under the own pet needs for its count and keys (CSS px). */
export const STRIP_WIDTH = 212;
/** The strip's height under the pet: 40px, less the 4px it tucks under the desk. */
export const STRIP_HEIGHT = 36;
/** Room on each side of the own name plate for its handle (`.own-plate` padding in App.vue). */
export const PLATE_GRIP = 14;

/**
 * The strip under the own pet at [scale]: laid out `layout` px wide and drawn `zoom` times as large, `width` px on
 * screen. A pet narrower than the strip shrinks the whole strip to its own width, so the strip never stands out on
 * the sides and keeps the pet away from the screen edges.
 */
export function stripFit(scale: number): { layout: number; zoom: number; width: number } {
  const pet = PET_BASE.width * scale;
  if (pet >= STRIP_WIDTH) return { layout: pet, zoom: 1, width: pet };
  return { layout: STRIP_WIDTH, zoom: pet / STRIP_WIDTH, width: pet };
}

/**
 * The own pet's width, the same whether the strip, the name plate or nothing is under it: the pet stands centred in
 * it and the actor is placed by its left edge, so a width that followed what is under the pet would move the pet
 * when the strip folds, click-through hides it, or the handle swaps in the plate.
 */
export function ownDeskWidth(scale: number): number {
  return Math.max(stripFit(scale).width, Math.round(PET_BASE.width * scale) + PLATE_GRIP * 2);
}
