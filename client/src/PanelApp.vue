<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import MainPanel from "./panel/MainPanel.vue";
import { listenInput, setMouseActive, writeLog } from "./composables/tauri";
import { watchLostClicks } from "./desktop/lostClicks";
import { resetOwnPet, viewport } from "./stores/desk";
import { onInput, stopPet } from "./stores/pet";
import { ui, type Page } from "./stores/ui";
import { windowVisible } from "./stores/activity";

const resize = () => { viewport.value = { w: window.innerWidth, h: window.innerHeight }; };
resize();
let unInput: (() => void) | undefined;
let unOpen: (() => void) | undefined;
let unVisibility: (() => void) | undefined;
let unFocus: (() => void) | undefined;
let unResize: (() => void) | undefined;
// Presses on the panel's buttons that never became clicks go to the log, for clicks that do nothing on macOS.
const unLost = watchLostClicks((msg) => writeLog("panel", msg),
  () => `, minimized ${ui.panelMinimized}, open ${ui.panelOpen}`);
let inputGeneration = 0;
const previewActive = computed(() => windowVisible.value && ui.panelOpen && !ui.panelMinimized && (ui.page === "emotes" || ui.page === "room"));
watch(previewActive, setMouseActive, { immediate: true });
watch(previewActive, async (active) => {
  const generation = ++inputGeneration;
  unInput?.();
  unInput = undefined;
  stopPet();
  if (active) {
    const unlisten = await listenInput((e) => onInput(e, false));
    if (generation === inputGeneration) unInput = unlisten;
    else unlisten();
  }
});

async function updateVisibility() {
  ui.panelMinimized = document.hidden || await getCurrentWindow().isMinimized();
}

onMounted(async () => {
  window.addEventListener("resize", resize);
  unVisibility = await listen<boolean>("panel:visible", ({ payload }) => {
    ui.panelOpen = payload;
    if (payload) ui.panelMinimized = false;
  }, { target: "panel" });
  unResize = await getCurrentWindow().onResized(updateVisibility);
  unFocus = await getCurrentWindow().onFocusChanged(updateVisibility);
  document.addEventListener("visibilitychange", updateVisibility);
  unOpen = await listen<{ page?: Page; craftTarget?: string }>("panel:open", ({ payload }) => {
    if (payload.page) ui.page = payload.page;
    if (payload.craftTarget !== undefined && payload.craftTarget !== null) ui.craftTarget = payload.craftTarget;
    ui.panelMinimized = false;
    ui.panelOpen = true;
  }, { target: "panel" });
  ui.panelOpen = true;
  await invoke("show_panel");
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  inputGeneration++;
  unInput?.();
  unOpen?.();
  unVisibility?.();
  unResize?.();
  unFocus?.();
  unLost();
  document.removeEventListener("visibilitychange", updateVisibility);
  stopPet();
});
</script>

<template>
  <KeepAlive><MainPanel v-if="ui.panelOpen && !ui.panelMinimized" @reset-pet="resetOwnPet" /></KeepAlive>
</template>
