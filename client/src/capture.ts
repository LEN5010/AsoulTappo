// Entry of the capture window (capture.html). Of the desk and the panel it shares the pet's drawing only:
// no player, no room, and it changes no settings (the desk tells it how the pet looks).
import { createApp } from "vue";
import "./ui/tokens.css";
import CaptureApp from "./CaptureApp.vue";
import { prepareWindow } from "./composables/tauri";

prepareWindow("capture");
createApp(CaptureApp).mount("#app");
