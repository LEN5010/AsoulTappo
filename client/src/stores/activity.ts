// Two reasons to stop drawing. A window that is not on screen (hidden, minimized, covered where the
// webview reports it) needs nothing painted. The desk that has shown nothing new for a while stops its
// looping decoration (name plate videos and sweeps, endless CSS animations); a key, the mouse or anything
// from the room starts it again. The panel never goes idle: a card video may be watched hands off.
import { computed, ref, watch } from "vue";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { isPanelWindow, isTauri } from "../composables/tauri";

/** The window is on screen. */
export const windowVisible = ref(true);
const idle = ref(false);
/** On screen, and something happened lately: looping decoration may run. */
export const renderActive = computed(() => windowVisible.value && !idle.value);
export const IDLE_MS = 30_000;
const idles = isTauri && !isPanelWindow;
let lastActivity = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

function checkIdle() {
  timer = undefined;
  if (!windowVisible.value) return;
  const remaining = IDLE_MS - (performance.now() - lastActivity);
  if (remaining > 0) timer = setTimeout(checkIdle, remaining);
  else idle.value = true;
}

/**
 * Something visible happened: local input (the global hook keeps reporting it while the pet is hidden, where
 * it starts nothing) or a room event. One timer runs per idle period, however many calls arrive.
 */
export function noteActivity() {
  if (!idles || !windowVisible.value) return;
  lastActivity = performance.now();
  idle.value = false;
  timer ??= setTimeout(checkIdle, IDLE_MS);
}

/** Endless animations only: one-shot ones belong to something that just happened and are left to finish. */
function loops(): Animation[] {
  return document.getAnimations().filter((a) => a.effect?.getComputedTiming().iterations === Infinity);
}

export async function startActivity(): Promise<() => void> {
  let nativeVisible = true;
  let told = false;
  const refresh = () => {
    windowVisible.value = nativeVisible && !document.hidden;
    clearTimeout(timer); timer = undefined;
    if (windowVisible.value) noteActivity();
  };
  const paused = new Set<Animation>();
  const stop = watch(renderActive, (active) => {
    if (active) {
      for (const animation of paused) if (animation.playState === "paused") animation.play();
      paused.clear();
    } else {
      for (const animation of loops()) if (animation.playState === "running") {
        animation.pause(); paused.add(animation);
      }
    }
  });
  document.addEventListener("visibilitychange", refresh);
  const events = ["pointerdown", "pointermove", "keydown"] as const;
  for (const event of events) window.addEventListener(event, noteActivity, { passive: true });
  // The desk is told when the pet is hidden from the tray or by the hotkey (src-tauri/src/lib.rs); the panel
  // follows ui.panelOpen and ui.panelMinimized (usePageActive).
  const unlisten = idles ? await listen<boolean>("window:visible", ({ payload }) => {
    told = true; nativeVisible = payload; refresh();
  }, { target: "main" }) : () => {};
  // Asked once as well, after listening: the window starts hidden and is shown about now, and whichever
  // of the two answers comes later is the newer one.
  if (idles) {
    const shown = await getCurrentWindow().isVisible().catch(() => true);
    if (!told) nativeVisible = shown;
  }
  refresh();
  return () => {
    clearTimeout(timer); timer = undefined; stop(); unlisten();
    document.removeEventListener("visibilitychange", refresh);
    for (const event of events) window.removeEventListener(event, noteActivity);
    paused.clear();
  };
}
