import { createApp } from "vue";
import "./ui/tokens.css";
import App from "./App.vue";
import PanelApp from "./PanelApp.vue";
import { isPanelWindow, writeLog } from "./composables/tauri";
import { initDesktop } from "./desktop/bridge";

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

async function main() {
  const stop = await initDesktop();
  window.addEventListener("beforeunload", stop, { once: true });
  createApp(isPanelWindow ? PanelApp : App).mount("#app");
}
void main();
