// Shared panel motion. Everything animates transform and opacity only, so a busy main
// thread (a heavy page mounting, say) cannot stall an animation that is already running.
import { reducedMotion } from "../stores/theme";

export const EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)";
export const EASE_IN_OUT = "cubic-bezier(0.76, 0, 0.24, 1)";
/** Matches --skew in tokens.css. */
export const SKEW = "skewX(-8deg)";
/** tan(8deg): horizontal run per pixel of height along the UI's slant. */
export const SLANT = 0.1405;

const RISE_MS = 360;
const RISE_STEP_MS = 18;
const RISE_MAX_STEPS = 10;

export const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

/**
 * Carries a copy of `src` from the `from` box onto `target`, then uncovers `target`. The copy
 * lives in the panel overlay because scrolling sheets would clip it on the way.
 */
export function flyFrom(from: DOMRect, target: HTMLElement, src: string): void {
  const host = target.closest(".panel-overlay");
  if (!host || reducedMotion.value) return;
  const to = target.getBoundingClientRect();
  const base = host.getBoundingClientRect();
  const ghost = new Image();
  ghost.src = src;
  ghost.alt = "";
  Object.assign(ghost.style, {
    position: "absolute",
    left: `${to.left - base.left}px`,
    top: `${to.top - base.top}px`,
    width: `${to.width}px`,
    height: `${to.height}px`,
    objectFit: "cover",
    transformOrigin: "0 0",
    pointerEvents: "none",
    zIndex: "45",
  });
  host.append(ghost);
  target.style.visibility = "hidden";
  const move = `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width})`;
  const flight = ghost.animate([{ transform: move }, { transform: "none" }], { duration: 340, easing: EASE_OUT });
  void flight.finished.catch(() => {}).finally(() => {
    ghost.remove();
    target.style.visibility = "";
  });
}

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
