import { onMounted, ref, type Ref } from "vue";

/** Room left between a plate opened upwards and what it clears, and kept to the screen's edges. */
const GAP = 10;
const EDGE = 4;

/**
 * How far a plate [width] px wide whose left edge rests at [left] moves sideways to stay [edge] px inside a viewport
 * [vw] px wide: plates hang from a strip narrower than they are, which may stand at the screen's edge. 0 when it fits;
 * a plate wider than the viewport keeps its left edge on screen.
 */
export function edgeShift(left: number, width: number, vw: number, edge = EDGE): number {
  if (left < edge) return Math.round(edge - left);
  const over = left + width - (vw - edge);
  return over > 0 ? Math.round(-Math.min(over, left - edge)) : 0;
}

/**
 * Where a plate hung under the strip opens: below it, or, where the screen ends below it, upwards. `ceiling` is the
 * viewport y the plate's bottom stays above, clear of the pet and the emote bubble over its head; with no room above
 * that either, or no ceiling, the plate opens right over the strip (the `.up` rule alone). Next to a side edge of the
 * screen it moves sideways by `--shift`, which the plate adds to its centring transform. Measured before the first
 * paint, so the plate never shows cut off first.
 */
export function useLift(root: Ref<HTMLElement | undefined>, ceiling: () => number | null | undefined) {
  const up = ref(false);
  const style = ref<Record<string, string>>({});
  onMounted(() => {
    const el = root.value;
    if (!el) return;
    const parent = (el.offsetParent as HTMLElement | null)?.getBoundingClientRect();
    // From the layout rather than the plate's own box, which the opening animation may still hold off its place.
    // The plate is centred on what it hangs from.
    const shift = parent ? edgeShift(parent.left + (parent.width - el.offsetWidth) / 2, el.offsetWidth, window.innerWidth) : 0;
    const next: Record<string, string> = shift ? { "--shift": `${shift}px` } : {};
    const r = el.getBoundingClientRect();
    if (r.bottom > window.innerHeight - EDGE) {
      up.value = true;
      const top = ceiling();
      const bottom = top == null ? 0 : top - GAP;
      if (top != null && parent && bottom - r.height >= EDGE) next.bottom = `${Math.round(parent.bottom - bottom)}px`;
    }
    style.value = next;
  });
  return { up, style };
}
