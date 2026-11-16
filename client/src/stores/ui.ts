import { reactive, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { isPanelWindow, isTauri } from "../composables/tauri";
import { settings } from "./settings";
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

let todoPopup: Window | null = null;
/**
 * The todos' own window, from the desk: opened where it was left, or shown and focused when it is open already. The
 * browser preview opens a popup of the same size.
 */
export function openTodoWindow(): void {
  ui.quickOpen = false;
  if (isTauri) {
    const placed = settings.todoX !== -1 || settings.todoY !== -1;
    void invoke("open_todo", { x: placed ? settings.todoX : null, y: placed ? settings.todoY : null, onTop: settings.todoPinned })
      .catch((e: unknown) => console.warn("open_todo failed", e));
    return;
  }
  if (todoPopup && !todoPopup.closed) { todoPopup.focus(); return; }
  todoPopup = window.open(`${import.meta.env.BASE_URL || "/"}?window=todo`, "asoultappo-todo", "popup,width=320,height=460");
}
