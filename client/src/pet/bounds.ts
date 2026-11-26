import { PET_BASE, headAnchor } from "../characters";
import type { Pos, Size } from "../stores/desk";
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
 * the sides and keeps the pet away from the screen edges. With [own] the strip is drawn at that size whatever the
 * pet's, as wide as the pet or wider; the caller keeps what stands out on screen.
 */
export function stripFit(scale: number, own?: number): { layout: number; zoom: number; width: number } {
  const pet = PET_BASE.width * scale;
  if (own != null) {
    const layout = Math.max(STRIP_WIDTH, pet / own);
    return { layout, zoom: own, width: layout * own };
  }
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

/**
 * The left edges the own pet's box ([width] px, ownDeskWidth) may take in a viewport [vw] px wide: the empty bands
 * beside the picture ([band] each) may stand out past the screen, so the picture reaches either side edge, but what
 * its second form draws past the picture on the right ([reach]) stays on screen.
 */
export function ownXRange(width: number, band: number, reach: number, vw: number): { min: number; max: number } {
  const min = -band;
  return { min, max: Math.max(min, vw - (width - band) - reach) };
}

/** What an emote takes over its anchor besides the picture: the point under it and the ×N badge's rise over it. */
const EMOTE_ROOM = 20;
/** Kept free between an emote and the top of the screen. */
const EMOTE_EDGE = 4;

/**
 * Where the emote over a pet at [pos] goes, as PetView's props: on the other side of the head next to the right screen
 * edge, and where the screen ends over it, down beside the head instead of off the screen. A pet above the screen's top
 * moves its emote no further than one standing at it. [min] is PetView's minEmote.
 */
export function emotePlace(pos: Pos, character: string, scale: number, min: number, vp: Size): { flipBubble: boolean; bubbleShift: Pos } {
  const size = Math.max(min, 72 * scale);
  const top = (headAnchor(character).y + 16) * scale - size - EMOTE_ROOM;
  const down = Math.max(0, Math.round(EMOTE_EDGE - top - Math.max(0, pos.y)));
  // Away from the face it would cover.
  const out = Math.round(Math.min(36 * scale, down * 0.6));
  const flipBubble = pos.x + 172 * scale + out + size + 24 > vp.w;
  return { flipBubble, bubbleShift: { x: flipBubble && out ? -out : out, y: down } };
}
