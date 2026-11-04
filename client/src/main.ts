import { createApp } from "vue";
import "./ui/tokens.css";
import App from "./App.vue";
import PanelApp from "./PanelApp.vue";
import { isPanelWindow } from "./composables/tauri";
import { initDesktop } from "./desktop/bridge";

async function main() {
  const stop = await initDesktop();
  window.addEventListener("beforeunload", stop, { once: true });
  createApp(isPanelWindow ? PanelApp : App).mount("#app");
}
void main();
