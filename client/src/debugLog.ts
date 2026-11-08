// Debug build only (see `debug_log` in src-tauri/src/lib.rs): what the desk page received and counted,
// and whether the browser engine considered it visible. Next to the Rust side's per-10-second line this
// tells a hook that heard nothing apart from a page that heard presses and did not count them.
import { tapCooldown, tapStats } from "./stores/pet";
import { writeLog } from "./composables/tauri";

const EVERY_MS = 10_000;
/** Quiet intervals in a row that still get a line, so a gap in the log means the page's timers stalled. */
const QUIET_EVERY = 6;

function pageState(): string {
  return `visibility ${document.visibilityState}, focus ${document.hasFocus()}, dpr ${globalThis.devicePixelRatio}, ` +
    `viewport ${innerWidth}x${innerHeight}`;
}

/** Starts the lines; `extra` adds the connection state. Returns a stop function. */
export function startDebugLog(extra: () => string): () => void {
  writeLog("debug", `page started: ${pageState()}`);
  const onVisibility = () => writeLog("debug", `visibility ${document.visibilityState}`);
  const onResize = () => writeLog("debug", `resize: ${pageState()}`);
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("resize", onResize);
  let quiet = 0;
  const timer = setInterval(() => {
    const s = { ...tapStats };
    tapStats.keys = tapStats.mouse = tapStats.counted = tapStats.blocked = 0;
    if (s.keys + s.mouse === 0 && ++quiet < QUIET_EVERY) return;
    quiet = 0;
    const left = Math.ceil((tapCooldown.value - Date.now()) / 1000);
    const cooling = left > 0 ? `, cooldown ${left}s left` : "";
    writeLog("debug", `page last ${EVERY_MS / 1000}s: key_down ${s.keys}, mouse_down ${s.mouse}, ` +
      `counted ${s.counted}, blocked ${s.blocked}${cooling}; ${pageState()}; ${extra()}`);
  }, EVERY_MS);
  return () => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("resize", onResize);
  };
}
