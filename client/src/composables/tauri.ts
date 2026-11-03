import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

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

export type TrayAction = "toggle-panel" | "toggle-click-through";

export async function listenTray(cb: (a: TrayAction) => void): Promise<UnlistenFn> {
  if (!isTauri) return () => {};
  return listen<TrayAction>("tray", (ev) => cb(ev.payload));
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
export const resizeWindow = (width: number, height: number) => call("resize_window", { width, height });
