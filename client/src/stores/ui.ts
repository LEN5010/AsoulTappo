import { reactive, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { isPanelWindow, isTauri } from "../composables/tauri";
export type Page = "emotes" | "resonance" | "dex" | "checkin" | "park" | "room" | "cheer" | "settings";
export const ui = reactive({ panelOpen: false, panelMinimized: false, page: "emotes" as Page, craftTarget: "", quickOpen: false });
// The scratch page became part of the park: a page named the old way (from the other window, say) opens the park.
watch(() => ui.page as string, (page) => { if (page === "scratch") ui.page = "park"; }, { flush: "sync", immediate: true });
export function openPanel(page?: Page, opts: { craftTarget?: string } = {}): void {
  if (page) ui.page = page;
  if (opts.craftTarget !== undefined || (isTauri && !isPanelWindow)) ui.craftTarget = opts.craftTarget ?? "";
  ui.panelOpen = true;
  ui.quickOpen = false;
  if (isTauri && !isPanelWindow) void invoke("open_panel", { page: ui.page, craftTarget: ui.craftTarget });
}
export function togglePanel(): void {
  if (isTauri && !isPanelWindow) { ui.quickOpen = false; void invoke("toggle_panel"); return; }
  if (ui.panelOpen) ui.panelOpen = false;
  else openPanel();
}
export function closePanel(): void {
  ui.panelOpen = false;
  if (isPanelWindow) void invoke("hide_panel");
}
