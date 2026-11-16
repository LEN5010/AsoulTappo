import type { Ref } from "vue";

/** Counts [out] to [to] over [ms], easing out; returns what cancels it. */
export function countTo(out: Ref<number>, to: number, ms: number): () => void {
  const from = out.value;
  const begin = performance.now();
  let frame = 0;
  const stepFrame = (t: number) => {
    const u = Math.min(1, (t - begin) / ms);
    out.value = Math.round(from + (to - from) * (1 - (1 - u) ** 3));
    if (u < 1) frame = requestAnimationFrame(stepFrame);
  };
  frame = requestAnimationFrame(stepFrame);
  return () => cancelAnimationFrame(frame);
}
