// One thumb that slides between the options of a tab strip. The resting box is set directly
// and the travel is a FLIP animation of transform, so moving it never touches layout.
import { onActivated, onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from "vue";
import { reducedMotion } from "../stores/theme";
import { EASE_OUT, SKEW } from "./motion";

interface Box { x: number; y: number; w: number; h: number }
const SLIDE_MS = 380;
const at = (b: Box) => `translate(${b.x}px, ${b.y}px)`;

/** `track` must be the offset parent of its `.on` option. */
export function useSlider(track: Ref<HTMLElement | undefined>, thumb: Ref<HTMLElement | undefined>, active: WatchSource): void {
  let last: Box | null = null;

  function place(animate: boolean) {
    const option = track.value?.querySelector<HTMLElement>(".on");
    const el = thumb.value;
    if (!el || !option?.offsetWidth) return;
    const to = { x: option.offsetLeft, y: option.offsetTop, w: option.offsetWidth, h: option.offsetHeight };
    const from = last;
    last = to;
    el.style.opacity = "1";
    el.style.width = `${to.w}px`;
    el.style.height = `${to.h}px`;
    el.style.transform = `${at(to)} ${SKEW}`;
    if (!animate || !from || reducedMotion.value) return;
    el.animate(
      [{ transform: `${at(from)} scaleX(${from.w / to.w}) ${SKEW}` }, { transform: `${at(to)} ${SKEW}` }],
      { duration: SLIDE_MS, easing: EASE_OUT },
    );
  }

  const observer = new ResizeObserver(() => place(false));
  watch(active, () => place(true), { flush: "post" });
  onMounted(() => {
    place(false);
    if (track.value) observer.observe(track.value);
    void document.fonts?.ready.then(() => place(false));
  });
  onActivated(() => place(false));
  onBeforeUnmount(() => observer.disconnect());
}
