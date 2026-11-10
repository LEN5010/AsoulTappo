import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { HitRect } from "../hit";

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
export const isPanelWindow = isTauri && new URLSearchParams(window.location.search).get("window") === "panel";

export type MouseButton = "left" | "right" | "middle" | "other";
/** Privacy-filtered input events from the Rust hook (src-tauri/src/input.rs). No key identity. */
export type InputEvent =
  | { kind: "key_down" }
  | { kind: "key_up" }
  | { kind: "mouse_down"; button: MouseButton }
  | { kind: "mouse_up"; button: MouseButton }
  | { kind: "mouse_move"; dx: number; dy: number };

/**
 * Subscribe to global input events. In Tauri these come from the Rust global
 * hook; in a plain browser (npm run dev) we fall back to DOM events so the UI
 * can be developed without the desktop shell.
 */
export async function listenInput(cb: (e: InputEvent) => void): Promise<() => void> {
  if (isTauri) {
    const un = await listen<InputEvent>("input", (ev) => cb(ev.payload));
    return un;
  }
  const down = new Set<string>();
  let last: { x: number; y: number } | null = null;
  const onKeyDown = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select")) return;
    if (down.has(e.code)) return;
    down.add(e.code);
    cb({ kind: "key_down" });
  };
  const onKeyUp = (e: KeyboardEvent) => {
    if (down.delete(e.code)) cb({ kind: "key_up" });
  };
  const btn = (b: number): MouseButton => (b === 0 ? "left" : b === 2 ? "right" : b === 1 ? "middle" : "other");
  const onDown = (e: MouseEvent) => cb({ kind: "mouse_down", button: btn(e.button) });
  const onUp = (e: MouseEvent) => cb({ kind: "mouse_up", button: btn(e.button) });
  const onMove = (e: MouseEvent) => {
    if (last) cb({ kind: "mouse_move", dx: e.clientX - last.x, dy: e.clientY - last.y });
    last = { x: e.clientX, y: e.clientY };
  };
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("mousedown", onDown);
  window.addEventListener("mouseup", onUp);
  window.addEventListener("mousemove", onMove);
  return () => {
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    window.removeEventListener("mousedown", onDown);
    window.removeEventListener("mouseup", onUp);
    window.removeEventListener("mousemove", onMove);
  };
}

export type TrayAction = "toggle-panel" | "open-panel" | "toggle-click-through" | "reset-position" | "toggle-capture";

export async function listenTray(cb: (a: TrayAction) => void): Promise<UnlistenFn> {
  if (!isTauri) return () => {};
  return listen<TrayAction>("tray", (ev) => cb(ev.payload));
}

/** Windows: whether the pet runs as administrator, whether this account could, and the player's choice. */
export interface AdminStatus { supported: boolean; elevated: boolean; canElevate: boolean; runAsAdmin: boolean }
export async function adminStatus(): Promise<AdminStatus | null> {
  if (!isTauri) return null;
  try {
    return await invoke<AdminStatus>("admin_status");
  } catch {
    return null;
  }
}
/**
 * Turns "start as administrator" on or off: "on" / "off", or "restarting" while the app restarts through UAC.
 * Rejects with "cancelled" when UAC was declined and "unavailable" when this account cannot run as administrator.
 */
export const setRunAsAdmin = (enabled: boolean) => invoke<"on" | "off" | "restarting">("set_run_as_admin", { enabled });

/** An elevated program stayed in front, so its keys and clicks cannot reach the pet; `by` is null once they can again. */
export interface InputBlocked { by: string | null; canElevate: boolean }
export async function listenInputBlocked(cb: (b: InputBlocked) => void): Promise<UnlistenFn> {
  if (!isTauri) return () => {};
  return listen<InputBlocked>("input-blocked", (ev) => cb(ev.payload));
}

/**
 * macOS: called with true while the hook lacks Input Monitoring and Accessibility, false once either is granted.
 * Reports the current state first, then each change.
 */
export async function listenInputAccess(cb: (missing: boolean) => void): Promise<UnlistenFn> {
  if (!isTauri) return () => {};
  const un = await listen<boolean>("input-access", (ev) => cb(ev.payload));
  try {
    cb(await invoke<boolean>("input_access_missing"));
  } catch {
    /* older shell without the command */
  }
  return un;
}
/** Opens the Input Monitoring page of System Settings. */
export const openInputSettings = () => call("open_input_settings", {});

/** A mouse press that fell through the overlay onto another window. */
export async function listenOutsideClick(cb: () => void): Promise<UnlistenFn> {
  if (!isTauri) return () => {};
  return listen("outside-click", () => cb());
}

async function call(cmd: string, args: Record<string, unknown>): Promise<void> {
  if (!isTauri) return;
  try {
    await invoke(cmd, args);
  } catch (e) {
    console.warn(`${cmd} failed`, e);
  }
}

export const setClickThrough = (enabled: boolean) => call("set_click_through", { enabled });
export const setAlwaysOnTop = (enabled: boolean) => call("set_always_on_top", { enabled });
/** Registers the hide key ("" removes it). Rejects when the system refuses the shortcut. */
export const setBossKey = (keys: string): Promise<void> => (isTauri ? invoke<void>("set_boss_key", { keys }) : Promise.resolve());
/**
 * Areas of the overlay (CSS px) that take the mouse; everything else lets clicks through.
 * `scale` is the page's device pixel ratio, used to turn CSS px into screen pixels.
 */
export const setHitRegions = (rects: HitRect[], scale: number) => call("set_hit_regions", { rects, scale });
/** Keep the overlay clickable while something is being dragged. */
export const setDragging = (active: boolean) => call("set_dragging", { active });

/** Where the exported log went: the desktop, or the downloads folder when that failed. */
export interface ExportedLog { path: string; desktop: boolean }

/** Copies the log next to the player (desktop, else downloads) and shows it in the file manager. */
export function exportLog(): Promise<ExportedLog> {
  if (!isTauri) return Promise.reject(new Error("not in the desktop app"));
  return invoke<ExportedLog>("export_log");
}

const LOG_LINES_PER_MINUTE = 30;
let logCap = LOG_LINES_PER_MINUTE;
let logMinute = 0;
let logLines = 0;
let lastLogLine = "";

/** Appends a line to the exportable log (tag `web:<tag>`); at most 30 a minute (240 in the debug build), repeats skipped. */
export function writeLog(tag: string, msg: string): void {
  if (!isTauri) return;
  const line = `${tag}\n${msg}`;
  if (line === lastLogLine) return;
  const now = Date.now();
  if (now - logMinute >= 60_000) {
    logMinute = now;
    logLines = 0;
  }
  if (logLines >= logCap) return;
  logLines += 1;
  lastLogLine = line;
  invoke("write_log", { tag, msg }).catch(() => {});
}

/** Whether this is the debug build for testers; there the page logs more and the per-minute cap is higher. */
export async function debugLogEnabled(): Promise<boolean> {
  if (!isTauri) return false;
  try {
    const on = await invoke<boolean>("debug_log");
    if (on) logCap = 240;
    return on;
  } catch {
    return false;
  }
}

/** Opens one of the About links (repository, author's space, mail) outside the app. */
export function openAboutLink(url: string): void {
  if (isTauri) void invoke("open_about_link", { url });
  else window.open(url, "_blank", "noopener");
}

/**
 * What every window does first: uncaught errors go to the exportable log tagged [kind], and the webview's
 * own context menu (reload, inspect) is left out of the app; text fields keep theirs for paste.
 */
export function prepareWindow(kind: string): void {
  const describe = (reason: unknown) => (reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason));
  window.addEventListener("error", (e) => writeLog(kind, `error: ${e.message} at ${e.filename}:${e.lineno}:${e.colno}`));
  window.addEventListener("unhandledrejection", (e) => writeLog(kind, `unhandled rejection: ${describe(e.reason)}`));
  if (import.meta.env.DEV) return;
  window.addEventListener("contextmenu", (e) => {
    if (!(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) e.preventDefault();
  });
}
