import { onMounted, ref, type Ref } from "vue";

/** Room left between a plate opened upwards and what it clears, and kept to the screen's top edge. */
const GAP = 10;
const EDGE = 4;

/**
 * Where a plate hung under the strip opens: below it, or, where the screen ends below it, upwards. `ceiling` is the
 * viewport y the plate's bottom stays above, clear of the pet and the emote bubble over its head; with no room above
 * that either, or no ceiling, the plate opens right over the strip (the `.up` rule alone). Measured before the first
 * paint, so the plate never shows cut off first.
 */
export function useLift(root: Ref<HTMLElement | undefined>, ceiling: () => number | null | undefined) {
  const up = ref(false);
  const style = ref<Record<string, string>>({});
  onMounted(() => {
    const el = root.value;
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (r.bottom <= window.innerHeight - EDGE) return;
    up.value = true;
    const top = ceiling();
    const parent = (el.offsetParent as HTMLElement | null)?.getBoundingClientRect();
    if (top == null || !parent) return;
    const bottom = top - GAP;
    if (bottom - r.height < EDGE) return;
    style.value = { bottom: `${Math.round(parent.bottom - bottom)}px` };
  });
  return { up, style };
}
