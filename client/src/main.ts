import { createApp } from "vue";
import "./ui/tokens.css";
import { isPanelWindow, writeLog } from "./composables/tauri";
import { initDesktop } from "./desktop/bridge";
import { startActivity } from "./stores/activity";

// Uncaught errors go to the exportable log, tagged by window.
const windowKind = isPanelWindow ? "panel" : "desk";
const describe = (reason: unknown) => (reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason));
window.addEventListener("error", (e) => writeLog(windowKind, `error: ${e.message} at ${e.filename}:${e.lineno}:${e.colno}`));
window.addEventListener("unhandledrejection", (e) => writeLog(windowKind, `unhandled rejection: ${describe(e.reason)}`));

// The webview's own context menu (reload, inspect) has no use in the app; text fields keep theirs for paste.
if (!import.meta.env.DEV) {
  window.addEventListener("contextmenu", (e) => {
    if (!(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) e.preventDefault();
  });
}

// One function per import. As the two arms of one conditional, the minifier folds them into a single
// preload call and the build gives both windows the desk's style sheets: the panel then has no frame.
const roots = { panel: () => import("./PanelApp.vue"), desk: () => import("./App.vue") };

async function main() {
  // Each window loads its own root only; the import runs while the desk state is fetched.
  const root = roots[isPanelWindow ? "panel" : "desk"]();
  const stopActivity = await startActivity();
  const stop = await initDesktop();
  window.addEventListener("beforeunload", () => { stopActivity(); stop(); }, { once: true });
  createApp((await root).default).mount("#app");
}
void main();
