import { createApp } from "vue";
import "./ui/tokens.css";
import { isPanelWindow, prepareWindow } from "./composables/tauri";
import { initDesktop } from "./desktop/bridge";
import { startActivity } from "./stores/activity";

prepareWindow(isPanelWindow ? "panel" : "desk");

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
