import { computed, onActivated, onDeactivated, ref } from "vue";
import { isPanelWindow } from "./tauri";
import { ui } from "../stores/ui";

/** Also follows KeepAlive ancestors when the native panel is hidden. */
export function usePageActive() {
  const mounted = ref(true);
  onActivated(() => { mounted.value = true; });
  onDeactivated(() => { mounted.value = false; });
  return computed(() => mounted.value && (!isPanelWindow || ui.panelOpen) && !ui.panelMinimized);
}
