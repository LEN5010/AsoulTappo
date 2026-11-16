// A card that leans toward the pointer and slowly comes back level once the pointer leaves.
import { onBeforeUnmount, ref, shallowRef } from "vue";
import { FLAT, MAX_TILT, tiltToward, type Tilt } from "./shader";

/** How fast the lean catches up: quick behind the pointer, slow on the way back. */
const FOLLOW_MS = 70;
const SETTLE_MS = 420;

/** `onSettle` runs when the card comes back level by itself after the pointer left, not on `reset`. */
export function useTilt(max = MAX_TILT, onSettle?: () => void) {
  const tilt = shallowRef<Tilt>(FLAT);
  /** The pointer is over the card. */
  const lit = ref(false);
  /** Leaning or on its way back: false once it is level again. */
  const moving = ref(false);
  let aim: Tilt | null = null;
  let frame = 0;
  let last = 0;

  function step(now: number) {
    const dt = Math.min(64, now - (last || now));
    last = now;
    const to = aim ?? FLAT;
    const k = 1 - Math.exp(-dt / (aim ? FOLLOW_MS : SETTLE_MS));
    const next = { rx: tilt.value.rx + (to.rx - tilt.value.rx) * k, ry: tilt.value.ry + (to.ry - tilt.value.ry) * k };
    const settled = !aim && Math.abs(next.rx) < 0.05 && Math.abs(next.ry) < 0.05;
    tilt.value = settled ? FLAT : next;
    if (settled) {
      frame = 0;
      last = 0;
      moving.value = false;
      onSettle?.();
      return;
    }
    frame = requestAnimationFrame(step);
  }
  function run() {
    moving.value = true;
    if (!frame) frame = requestAnimationFrame(step);
  }

  /** Leans toward the pointer over `el`. */
  function follow(e: PointerEvent, el: Element | null | undefined) {
    const box = el?.getBoundingClientRect();
    if (!box?.width || !box.height) return;
    aim = tiltToward((e.clientX - box.left) / box.width, (e.clientY - box.top) / box.height, max);
    lit.value = true;
    run();
  }
  function leave() {
    if (!aim && !lit.value) return;
    aim = null;
    lit.value = false;
    run();
  }
  /** Level at once, as when the card changes. */
  function reset() {
    aim = null;
    lit.value = false;
    cancelAnimationFrame(frame);
    frame = 0;
    last = 0;
    tilt.value = FLAT;
    moving.value = false;
  }
  onBeforeUnmount(() => cancelAnimationFrame(frame));
  return { tilt, lit, moving, follow, leave, reset };
}
