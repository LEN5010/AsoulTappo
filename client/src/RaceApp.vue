<script setup lang="ts">
// The race's own window (`?window=race`; src-tauri/src/lib.rs, open_race): the page that watches a race
// (panel/park/RaceWatch.vue) on a transparent window, shown once it has drawn. `replay` in the address is the
// finished race to play, none for the live one; a window already open is told what to play (`race:open`). Closing
// it closes the window: it is made again the next time.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import RaceWatch from "./panel/park/RaceWatch.vue";

const replay = ref(Number(new URLSearchParams(location.search).get("replay")) || 0);
/** Counts what the window was told to play: each a fresh start. */
const n = ref(0);
let unOpen: (() => void) | undefined;

onMounted(async () => {
  unOpen = await listen<number | null>("race:open", ({ payload }) => {
    replay.value = payload ?? 0;
    n.value++;
  }, { target: "race" });
  await invoke("show_race").catch(() => {});
});
onBeforeUnmount(() => unOpen?.());
</script>

<template>
  <RaceWatch :key="n" :replay="replay" @close="invoke('close_race')" @drag="getCurrentWindow().startDragging()" />
</template>
