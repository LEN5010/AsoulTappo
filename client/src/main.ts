import { createApp } from "vue";
import "./ui/tokens.css";
import { isPanelWindow, isTodoWindow, prepareWindow } from "./composables/tauri";
import { startActivity } from "./stores/activity";

const kind = isPanelWindow ? "panel" : isTodoWindow ? "todo" : "desk";
prepareWindow(kind);

// One function per import. As the two arms of one conditional, the minifier folds them into a single
// preload call and the build gives both windows the desk's style sheets: the panel then has no frame.
const roots = { panel: () => import("./PanelApp.vue"), todo: () => import("./TodoApp.vue"), desk: () => import("./App.vue") };

async function main() {
  // Each window loads its own root only; the import runs while the desk state is fetched.
  const root = roots[kind]();
  // The todos' window holds the list and the settings only: the desk's bridge would load the network stores.
  if (kind === "todo") {
    const { initTodoWindow } = await import("./desktop/todoBridge");
    const stop = await initTodoWindow();
    window.addEventListener("beforeunload", stop, { once: true });
    createApp((await root).default).mount("#app");
    return;
  }
  const { initDesktop } = await import("./desktop/bridge");
  const stopActivity = await startActivity();
  const stop = await initDesktop();
  window.addEventListener("beforeunload", () => { stopActivity(); stop(); }, { once: true });
  createApp((await root).default).mount("#app");
}
void main();
