<script setup lang="ts">
// The dou dizhu table's own window (`?window=ddz`; src-tauri/src/lib.rs, open_ddz): the table
// (panel/ddz/DdzTable.vue) on a transparent window, shown once it has drawn. It mirrors the desk's state
// (desktop/bridge.ts) and sends the moves there; it talks to no server. The desk opens it with each deal and closes it
// once the table is put away. Closing it leaves the seat playing (the server's autopilot moves when the time runs
// out). A game of the room being watched shows here too while the save has none of its own; closing the window then
// stops watching (the desk hears of it, stores/ddz.ts noteDdzWindowClosed).
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { wakeAudio } from "./audio/sfx";
import { listenInput } from "./composables/tauri";
import DdzTable from "./panel/ddz/DdzTable.vue";
import { ddzScreen, ddzWatch } from "./stores/ddz";
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
// The own pet beside the hand moves with the keys and the mouse while the table is in sight and it is the save's own
// game (a watched game shows the players' pets as the room sends them); the desk counts the taps either way.
let inputGeneration = 0;
const previewActive = computed(() => ui.ddzSeen && ddzScreen.value === "own");
watch(previewActive, async (active) => {
  const generation = ++inputGeneration;
  unInput?.();
  unInput = undefined;
  stopPet();
  if (!active) return;
  const unlisten = await listenInput((e) => onInput(e, false));
  if (generation === inputGeneration) unInput = unlisten;
  else unlisten();
}, { immediate: true });
onMounted(async () => {
  unResize = await getCurrentWindow().onResized(updateSeen);
  unFocus = await getCurrentWindow().onFocusChanged(updateSeen);
  document.addEventListener("visibilitychange", updateSeen);
  await updateSeen();
  // The deal's sounds come before any click on a fresh window.
  wakeAudio();
  await invoke("show_ddz").catch(() => {});
});
onBeforeUnmount(() => {
  inputGeneration++;
  unInput?.();
  unResize?.();
  unFocus?.();
  document.removeEventListener("visibilitychange", updateSeen);
  stopPet();
});
</script>

<template>
  <div class="ddz-app" :style="skinVars">
    <DdzTable
      v-if="ddzScreen" :key="ddzScreen === 'watch' ? `watch:${ddzWatch?.id}` : 'own'"
      @close="close" @drag="getCurrentWindow().startDragging()"
    />
  </div>
</template>

<style>
html, body, #app { margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }
body { font-family: var(--font); color: var(--ink); -webkit-font-smoothing: antialiased; }
.ddz-app { position: fixed; inset: 0; }
</style>
