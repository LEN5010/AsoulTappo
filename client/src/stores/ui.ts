import { reactive } from "vue";
import { settings } from "./settings";
export type Page = "dex" | "emotes" | "room" | "settings";
export const ui = reactive({ panelOpen: false, page: "dex" as Page, craftTarget: "", quickOpen: false });
export function openPanel(page?: Page, opts: { craftTarget?: string } = {}): void {
  if (settings.clickThrough) return;
  if (page) ui.page = page;
  if (opts.craftTarget !== undefined) ui.craftTarget = opts.craftTarget;
  ui.panelOpen = true;
  ui.quickOpen = false;
}
export function togglePanel(): void { if (ui.panelOpen) ui.panelOpen = false; else openPanel(); }
