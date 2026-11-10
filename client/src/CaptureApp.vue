<script setup lang="ts">
// The own pet as it stands on the desk (emote bubble, shard pops, the strip with the tap count) alone on a
// flat colour, as large as the window allows. Recording software keys the colour out.
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { emitTo, listen } from "@tauri-apps/api/event";
import PetView from "./pet/PetView.vue";
import CounterBar from "./pet/CounterBar.vue";
import { PetPose } from "./pet/PetPose";
import { defaultCharacter, PET_BASE } from "./characters";
import { isTauri, listenInput } from "./composables/tauri";
import type { CaptureView } from "./desktop/capture";

const view = reactive<CaptureView>({
  character: defaultCharacter, sensitivity: 0.3, bg: "#00ff00",
  bar: { count: 0, view: "today", draws: 0 }, emote: null, combo: null, win: null,
});
// In the app the pet waits for the desk to say which one it is.
const ready = ref(!isTauri);
const pose = new PetPose();
const pet = pose.pet;

// Room around the pet's canvas for what stands out of it, in the canvas's own px: the emote bubble rises from
// the head and grows to the right, the strip hangs below.
const ROOM = { top: 72, right: 96, bar: 40 };
const stage = computed(() => ({
  w: PET_BASE.width + ROOM.right, h: ROOM.top + PET_BASE.height + (view.bar ? ROOM.bar : 0),
}));
const size = ref({ w: window.innerWidth, h: window.innerHeight });
const scale = computed(() => Math.min(size.value.w / stage.value.w, size.value.h / stage.value.h));
const px = (v: number) => `${v * scale.value}px`;
const resize = () => { size.value = { w: window.innerWidth, h: window.innerHeight }; };
const stops: (() => void)[] = [];

onMounted(async () => {
  window.addEventListener("resize", resize);
  // The window is usually behind the game being recorded, so the pet moves whether or not it is in front.
  stops.push(await listenInput((e) => pose.input(e, view.sensitivity)));
  if (!isTauri) return;
  stops.push(await listen<CaptureView>("capture:view", ({ payload }) => {
    Object.assign(view, payload);
    if (payload.sensitivity === null) pose.stopMouse();
    ready.value = true;
  }, { target: "capture" }));
  await emitTo("main", "capture:ready");
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  stops.forEach((stop) => stop());
  pose.stop();
});
</script>

<template>
  <div class="capture" :style="{ background: view.bg }" @dragstart.prevent>
    <div
      v-if="ready" class="stage"
      :style="{ width: px(stage.w), height: px(stage.h), paddingTop: px(ROOM.top), '--bubble-max-width': px(160) }"
    >
      <PetView
        :character="view.character" :scale="scale" :key-down="pet.keyDown"
        :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right"
        :emote="view.emote" :combo="view.combo" combo-icon="shard" :win="view.win" :min-emote="56"
      />
      <!-- Laid out at the canvas's size and enlarged with it, keys and all: a picture of the strip, nothing to press. -->
      <CounterBar
        v-if="view.bar" class="strip" :style="{ zoom: scale }"
        :count="view.bar.count" :view="view.bar.view" :draws="view.bar.draws" :width="PET_BASE.width" :quick-open="false"
      />
    </div>
  </div>
</template>

<style>
html, body, #app { height: 100%; margin: 0; overflow: hidden; }
</style>
<style scoped>
.capture { height: 100%; display: grid; place-items: center; user-select: none; }
.stage { box-sizing: border-box; pointer-events: none; }
/* A soft shadow on the flat colour is left behind as a dark fringe when the colour is keyed out. */
.strip { box-shadow: none; }
</style>
