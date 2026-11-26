// Whether an element is in the viewport, for what only needs to run where it can be seen (a name plate's video and
// sweep). One IntersectionObserver serves every element.
import { onScopeDispose, ref, watch, type Ref } from "vue";

const listeners = new WeakMap<object, (visible: boolean) => void>();
let shared: IntersectionObserver | null = null;

function observe(el: Element, cb: (visible: boolean) => void): () => void {
  shared ??= new IntersectionObserver((entries) => {
    for (const entry of entries) listeners.get(entry.target)?.(entry.isIntersecting);
  });
  listeners.set(el, cb);
  shared.observe(el);
  return () => {
    listeners.delete(el);
    shared?.unobserve(el);
  };
}

/**
 * Whether [el] is in the viewport, followed while [watching] holds; false until the observer first tells, and while
 * not watched. Where there is no IntersectionObserver everything counts as in view.
 */
export function useInView(el: Ref<object | null | undefined>, watching: () => boolean): Ref<boolean> {
  const supported = typeof IntersectionObserver !== "undefined";
  const inView = ref(!supported);
  let stop: (() => void) | undefined;
  watch([el, watching], ([node, on]) => {
    stop?.();
    stop = undefined;
    if (!supported) return;
    inView.value = false;
    if (!node || !on) return;
    stop = observe(node as Element, (visible) => { inView.value = visible; });
  }, { immediate: true, flush: "post" });
  onScopeDispose(() => stop?.());
  return inView;
}
