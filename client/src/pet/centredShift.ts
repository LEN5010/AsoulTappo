import { computed, onScopeDispose, ref, watch, type Ref } from "vue";

/**
 * How far a bubble [width] px wide, centred over viewport x [middle], moves sideways to stay [margin] px inside a
 * screen [vw] px wide. 0 when it fits; a bubble wider than the screen keeps its left edge on it.
 */
export function centredShift(middle: number, width: number, vw: number, margin = 8): number {
  const left = middle - width / 2;
  const fitted = Math.min(Math.max(left, margin), Math.max(margin, vw - margin - width));
  return Math.round(fitted - left);
}

/** The own pet's middle in viewport x, and the viewport's width. */
export type PetMiddle = { x: number; w: number };

/**
 * The sideways shift of a bubble over the own pet that sizes to its text (the cooldown, a park win, the admin and
 * permission notes, the automatic-input alert), measured from the bubble [el] itself while it shows: at a side edge
 * of the screen it moves in the way the fixed-width bubbles do (bubblePlacement), its point staying on the pet.
 * With no [middle] it stays centred.
 */
export function useCentredShift(el: Ref<HTMLElement | null | undefined>, middle: () => PetMiddle | undefined) {
  const width = ref(0);
  let seen: ResizeObserver | undefined;
  const stop = () => {
    seen?.disconnect();
    seen = undefined;
  };
  watch(el, (node) => {
    stop();
    width.value = node?.offsetWidth ?? 0;
    if (!node || typeof ResizeObserver === "undefined") return;
    seen = new ResizeObserver(() => { width.value = node.offsetWidth; });
    seen.observe(node);
  }, { immediate: true, flush: "post" });
  onScopeDispose(stop);
  return computed(() => {
    const m = middle();
    return m && width.value ? centredShift(m.x, width.value, m.w) : 0;
  });
}
