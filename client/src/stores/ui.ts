// Which panel page is open and small cross-component UI state.
import { reactive } from "vue";
import { settings } from "./settings";

export type Page = "bag" | "dex" | "craft" | "room" | "settings";
export type BagTab = "recent" | "character" | "accessory" | "emote" | "card" | "dress";

export const ui = reactive({
  panelOpen: false,
  page: "bag" as Page,
  bagTab: "recent" as BagTab,
  /** item preselected in the craft page */
  craftTarget: "",
  quickOpen: false,
});

export function openPanel(page?: Page, opts: { bagTab?: BagTab; craftTarget?: string } = {}): void {
  if (settings.clickThrough) return; // the overlay cannot take clicks
  if (page) ui.page = page;
  if (opts.bagTab) ui.bagTab = opts.bagTab;
  if (opts.craftTarget !== undefined) ui.craftTarget = opts.craftTarget;
  ui.panelOpen = true;
  ui.quickOpen = false;
}

export function togglePanel(): void {
  if (ui.panelOpen) ui.panelOpen = false;
  else openPanel();
}
