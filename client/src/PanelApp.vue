<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import MainPanel from "./panel/MainPanel.vue";
import { listenInput } from "./composables/tauri";
import { viewport } from "./stores/desk";
import { settings } from "./stores/settings";
import { onInput, stopPet } from "./stores/pet";
import { ui, type Page } from "./stores/ui";

const resize = () => { viewport.value = { w: window.innerWidth, h: window.innerHeight }; };
resize();
let unInput: (() => void) | undefined;
let unOpen: (() => void) | undefined;

function resetPet() { settings.petX = -1; settings.petY = -1; }

onMounted(async () => {
  window.addEventListener("resize", resize);
  // The preview animates from input; counting remains in the desk window.
  unInput = await listenInput((e) => onInput(e, false));
  unOpen = await listen<{ page?: Page; craftTarget?: string }>("panel:open", ({ payload }) => {
    if (payload.page) ui.page = payload.page;
    if (payload.craftTarget !== undefined && payload.craftTarget !== null) ui.craftTarget = payload.craftTarget;
    ui.panelOpen = true;
  }, { target: "panel" });
  ui.panelOpen = true;
  await invoke("show_panel");
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  unInput?.();
  unOpen?.();
  stopPet();
});
</script>

<template>
  <MainPanel @reset-pet="resetPet" />
</template>
