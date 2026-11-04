// Shared panel motion. Everything animates transform and opacity only, so a busy main
// thread (a heavy page mounting, say) cannot stall an animation that is already running.
import { reducedMotion } from "../stores/theme";

export const EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)";
/** tan(8deg): horizontal run per pixel of height along the UI's slant. */
export const SLANT = 0.1405;

const RISE_MS = 460;
const RISE_STEP_MS = 24;
const RISE_MAX_STEPS = 14;

export const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

/**
 * Stagger the `[data-rise]` elements of `scope` that are inside `view` along the slant.
 * Elements below the fold appear without animation, which keeps long grids cheap.
 */
export function rise(scope: Element | null | undefined, view: Element | null | undefined = scope, delay = 0): void {
  if (!scope || !view || reducedMotion.value) return;
  const box = view.getBoundingClientRect();
  let i = 0;
  for (const el of scope.querySelectorAll<HTMLElement>("[data-rise]")) {
    const r = el.getBoundingClientRect();
    if (r.top > box.bottom) break;
    if (r.bottom < box.top) continue;
    el.animate(
      [{ opacity: 0, transform: "translate(-12px, 18px)" }, { opacity: 1, transform: "none" }],
      { duration: RISE_MS, delay: delay + Math.min(i++, RISE_MAX_STEPS) * RISE_STEP_MS, easing: EASE_OUT, fill: "backwards" },
    );
  }
}
