import { reactive, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { isPanelWindow, isTauri } from "../composables/tauri";
import { settings } from "./settings";
export type Page = "emotes" | "resonance" | "dex" | "checkin" | "park" | "room" | "cheer" | "settings";
export const ui = reactive({
  panelOpen: false, panelMinimized: false, page: "emotes" as Page, craftTarget: "", quickOpen: false,
  /** The collection's page opens on this card filter once (the resonance page's holo collection asks for "holo"). */
  dexFilter: "" as "" | "holo",
  /** The pool on show on the resonance page: a limited pool's id, or "" for the standing pool. */
  pool: "",
  /** Desk window only: the dou dizhu table's window is open and not minimized, as it last reported (desktop/bridge.ts). */
  ddzSeen: false,
});
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
/** The desk's key for the panel: brings it to the front on the page it shows, never hides it (the tray toggles it). */
export function raisePanel(): void {
  ui.quickOpen = false;
  if (isTauri && !isPanelWindow) void invoke("open_panel", {});
  else openPanel();
}
export function closePanel(): void {
  ui.panelOpen = false;
  if (isPanelWindow) void invoke("hide_panel");
}

/** The browser preview's todos' window: a frame over the desk page (pet/TodoFrame.vue), where it was left. */
export const todoFrame = reactive({ open: false, x: -1, y: -1, w: 0, h: 0 });
/**
 * The todos' own window, from the desk: opened where it was left, or shown and focused when it is open already. The
 * browser preview floats the same page in a frame of the same size over the desk page.
 */
export function openTodoWindow(): void {
  ui.quickOpen = false;
  if (isTauri) {
    const placed = settings.todoX !== -1 || settings.todoY !== -1;
    void invoke("open_todo", {
      x: placed ? settings.todoX : null, y: placed ? settings.todoY : null, w: settings.todoW, h: settings.todoH, onTop: settings.todoPinned,
    })
      .catch((e: unknown) => console.warn("open_todo failed", e));
    return;
  }
  todoFrame.open = true;
}

/**
 * The browser preview's race window: a frame over the desk page (pet/RaceFrame.vue). `replay`: the finished race it
 * plays, 0 for the live one; `n` counts the openings, each a fresh start.
 */
export const raceFrame = reactive({ open: false, replay: 0, n: 0 });
/**
 * The race's own window, from the desk or the panel: the live race, or finished race [replay] played again. Opened,
 * or shown and told what to play when it is open already.
 */
export function openRaceWindow(replay = 0): void {
  ui.quickOpen = false;
  if (isTauri) {
    void invoke("open_race", { replay: replay || null }).catch((e: unknown) => console.warn("open_race failed", e));
    return;
  }
  raceFrame.replay = replay;
  raceFrame.n++;
  raceFrame.open = true;
}

/** The browser preview's dou dizhu window: a frame over the desk page (pet/DdzFrame.vue). */
export const ddzFrame = reactive({ open: false });
/**
 * The dou dizhu table's own window, from the desk or the panel: opened, or shown and focused when it is open already.
 * The browser preview floats the table in a frame of the window's size over the desk page.
 */
export function openDdzWindow(): void {
  ui.quickOpen = false;
  if (isTauri) {
    void invoke("open_ddz").catch((e: unknown) => console.warn("open_ddz failed", e));
    return;
  }
  ddzFrame.open = true;
}
/** Closes the table's window; the game goes on without it. */
export function closeDdzWindow(): void {
  if (isTauri) {
    void invoke("close_ddz").catch((e: unknown) => console.warn("close_ddz failed", e));
    return;
  }
  ddzFrame.open = false;
}
