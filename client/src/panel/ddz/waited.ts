// The time a save has waited in the dou dizhu queue, as m:ss, ticking once a second while it waits.
import { computed, onBeforeUnmount, ref, watch } from "vue";

/** m:ss of [sec] seconds. */
export const mmss = (sec: number): string => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

/** The time since [since] (local ms) as m:ss, ticking while [since] gives a time; "0:00" while it gives none. */
export function useWaited(since: () => number | undefined) {
  const now = ref(Date.now());
  let ticker: ReturnType<typeof setInterval> | undefined;
  watch(since, (at) => {
    clearInterval(ticker);
    now.value = Date.now();
    if (at !== undefined) ticker = setInterval(() => { now.value = Date.now(); }, 1000);
  }, { immediate: true });
  onBeforeUnmount(() => clearInterval(ticker));
  return computed(() => mmss(Math.max(0, Math.floor((now.value - (since() ?? now.value)) / 1000))));
}
