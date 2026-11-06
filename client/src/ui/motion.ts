// Shared panel motion. Everything animates transform and opacity only, so a busy main
// thread (a heavy page mounting, say) cannot stall an animation that is already running.
import { reducedMotion } from "../stores/theme";

export const EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)";
export const EASE_IN_OUT = "cubic-bezier(0.76, 0, 0.24, 1)";

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
 * Stagger the `[data-rise]` elements of `scope` that are inside `view`.
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

const ARC_MS = 420;
const ARC_STEPS = 6;
/**
 * Flies a copy of `src` along a short arc from the `from` box to the `to` box, as a sticker thrown
 * onto a key or peeled back off it. With no `to` the copy drops a little and fades where it is.
 * The copy lives in the panel overlay, so scroll containers cannot clip it; `host` is any element
 * inside the panel. Resolves when the flight is over (at once under reduced motion).
 */
export function flyArc(host: Element, src: string, from: DOMRect, to: DOMRect | null, peel = false): Promise<void> {
  const overlay = host.closest(".panel")?.querySelector(".panel-overlay");
  if (!overlay || reducedMotion.value || !from.width) return Promise.resolve();
  const base = overlay.getBoundingClientRect();
  const end = to ?? new DOMRect(from.left, from.top + 28, from.width, from.height);
  const ghost = new Image();
  ghost.src = src;
  ghost.alt = "";
  Object.assign(ghost.style, {
    position: "absolute",
    left: `${end.left - base.left}px`,
    top: `${end.top - base.top}px`,
    width: `${end.width}px`,
    height: `${end.height}px`,
    objectFit: "contain",
    filter: "var(--sticker)",
    transformOrigin: "50% 50%",
    pointerEvents: "none",
    zIndex: "45",
  });
  overlay.append(ghost);
  const dx = from.left + from.width / 2 - (end.left + end.width / 2);
  const dy = from.top + from.height / 2 - (end.top + end.height / 2);
  const scale = from.width / end.width;
  const lift = to ? Math.min(90, 24 + Math.hypot(dx, dy) * 0.18) : 0;
  // Sampled from a quadratic curve whose control point sits above the midpoint.
  const frames: Keyframe[] = Array.from({ length: ARC_STEPS + 1 }, (_, i) => {
    const t = i / ARC_STEPS;
    const x = dx * (1 - t);
    const y = dy * (1 - t) - 4 * lift * t * (1 - t);
    const s = scale + (1 - scale) * t;
    const turn = peel ? -10 * Math.sin(Math.PI * t) : 6 * Math.sin(Math.PI * t);
    return { transform: `translate(${x}px, ${y}px) rotate(${turn}deg) scale(${s})`, opacity: to ? 1 : 1 - t };
  });
  const flight = ghost.animate(frames, { duration: to ? ARC_MS : 300, easing: to ? EASE_IN_OUT : "ease-in" });
  return flight.finished.catch(() => undefined).then(() => ghost.remove());
}

/** The landing of a stuck-on sticker: squashed flat, then a little proud, then at rest. */
export function squash(el: Element | null | undefined): void {
  if (!el || reducedMotion.value) return;
  el.animate(
    [{ transform: "scale(0.92, 0.92)" }, { transform: "scale(1.04, 1.04)", offset: 0.55 }, { transform: "scale(1, 1)" }],
    { duration: 260, easing: "ease-out" },
  );
}
