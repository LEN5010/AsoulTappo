// Where the bubbles over the own pet go: placed from the box the pet is drawn in, which a drag moves before the
// pet's place is saved, so a bubble stays on screen while the pet is carried to a side edge.
import { computed, type ComputedRef } from "vue";
import type { Pos, Size } from "../stores/desk";
import type { PetMiddle } from "./centredShift";
import { bubblePlacement } from "./duelPick";

/** [at] is the own pet's box as drawn (the drag's place while it is dragged), [size] its size, [screen] the viewport. */
export function ownBubbles(at: () => Pos, size: () => Size, screen: () => Size) {
  /** The pet's middle and the screen's width, for the bubbles that size to their text (centredShift.ts). */
  const middle = computed<PetMiddle>(() => ({ x: at().x + size().w / 2, w: screen().w }));
  /** Placement of a fixed-size bubble over the pet (bubblePlacement). */
  const place = (bubble: Size | (() => Size)): ComputedRef<{ shift: number; below: boolean }> =>
    computed(() => bubblePlacement(at(), size(), typeof bubble === "function" ? bubble() : bubble, screen()));
  return { middle, place };
}
