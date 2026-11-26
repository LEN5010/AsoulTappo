// Another member's pet keeps its endless animations (a second form's loop frames) going on that member's own clock:
// the desk's idle clock (stores/activity.ts) pauses every endless animation once this desk has had no input for a
// while, which partners' taps no longer reset. Here a partner's loops play on while the partner taps, moves or
// changes form, and rest with the desk's once the partner has been quiet as long.
import { computed, onScopeDispose, ref, watch, type Ref } from "vue";
import { IDLE_MS, renderActive, windowVisible } from "../stores/activity";

interface Loop {
  readonly playState: AnimationPlayState;
  readonly effect: { getComputedTiming(): { iterations?: number } } | null;
  play(): void;
  pause(): void;
}
interface Animated { getAnimations(options?: GetAnimationsOptions): Loop[] }

/**
 * The endless animations inside [el] (a partner's pet) while [enabled]; [signals] changes with the partner's
 * activity (tap batches, the form). `note` counts other activity (the room's motion updates).
 */
export function usePartnerLoops(el: Ref<Animated | null | undefined>, enabled: () => boolean, signals: () => unknown) {
  const quiet = ref(true);
  let timer: ReturnType<typeof setTimeout> | undefined;
  function note() {
    if (!enabled()) return;
    quiet.value = false;
    clearTimeout(timer);
    timer = setTimeout(() => { quiet.value = true; }, IDLE_MS);
  }
  watch(signals, note);
  /** On screen, and either the desk or this partner did something lately. */
  const run = computed(() => renderActive.value || (windowVisible.value && !quiet.value));
  // After the desk's own pause and resume (its watcher runs before these post-flush ones), and after a loop mounts.
  watch([run, el, signals], () => {
    const node = el.value;
    if (!enabled() || !node?.getAnimations) return;
    for (const a of node.getAnimations({ subtree: true })) {
      if (a.effect?.getComputedTiming().iterations !== Infinity) continue;
      if (run.value && a.playState === "paused") a.play();
      else if (!run.value && a.playState === "running") a.pause();
    }
  }, { flush: "post" });
  onScopeDispose(() => clearTimeout(timer));
  return { note };
}
