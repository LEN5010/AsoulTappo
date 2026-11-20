<script setup lang="ts">
// The dou dizhu table's own window (`?window=ddz`; src-tauri/src/lib.rs, open_ddz): the table
// (panel/ddz/DdzTable.vue) on a transparent window, shown once it has drawn. It mirrors the desk's state
// (desktop/bridge.ts) and sends the moves there; it talks to no server. The desk opens it with each deal and closes it
// once the table is put away. Closing it leaves the seat playing (the server's autopilot moves when the time runs
// out).
import { onBeforeUnmount, onMounted } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { wakeAudio } from "./audio/sfx";
import { listenInput } from "./composables/tauri";
import DdzTable from "./panel/ddz/DdzTable.vue";
import { ddzAtTable } from "./stores/ddz";
import { onInput, stopPet } from "./stores/pet";
import { skinVars } from "./stores/theme";
import { ui } from "./stores/ui";

const close = () => { void invoke("close_ddz").catch(() => {}); };

/** Tells the desk whether the window is in sight: while it is not, the pet's bubble says whose move it is. */
async function updateSeen() {
  ui.ddzSeen = !document.hidden && !(await getCurrentWindow().isMinimized().catch(() => false));
}

let unInput: (() => void) | undefined;
let unResize: (() => void) | undefined;
let unFocus: (() => void) | undefined;
onMounted(async () => {
  // The own pet beside the hand moves with the keys and the mouse; the desk counts the taps.
  unInput = await listenInput((e) => onInput(e, false));
  unResize = await getCurrentWindow().onResized(updateSeen);
  unFocus = await getCurrentWindow().onFocusChanged(updateSeen);
  document.addEventListener("visibilitychange", updateSeen);
  await updateSeen();
  // The deal's sounds come before any click on a fresh window.
  wakeAudio();
  await invoke("show_ddz").catch(() => {});
});
onBeforeUnmount(() => {
  unInput?.();
  unResize?.();
  unFocus?.();
  document.removeEventListener("visibilitychange", updateSeen);
  stopPet();
});
</script>

<template>
  <div class="ddz-app" :style="skinVars">
    <DdzTable v-if="ddzAtTable" @close="close" @drag="getCurrentWindow().startDragging()" />
  </div>
</template>

<style>
html, body, #app { margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }
body { font-family: var(--font); color: var(--ink); -webkit-font-smoothing: antialiased; }
.ddz-app { position: fixed; inset: 0; }
</style>
