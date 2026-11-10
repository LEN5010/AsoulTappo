import { computed, onActivated, onDeactivated, ref } from "vue";
import { isPanelWindow } from "./tauri";
import { ui } from "../stores/ui";
import { windowVisible } from "../stores/activity";

/** Whether a component may be seen: its window is on screen, its KeepAlive page is the shown one, and the
 * native panel is open. */
export function usePageActive() {
  const mounted = ref(true);
  onActivated(() => { mounted.value = true; });
  onDeactivated(() => { mounted.value = false; });
  return computed(() => mounted.value && windowVisible.value && (!isPanelWindow || (ui.panelOpen && !ui.panelMinimized)));
}
