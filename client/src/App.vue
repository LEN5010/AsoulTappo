<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import PetView from "./components/PetView.vue";
import RoomPanel from "./components/RoomPanel.vue";
import SettingsPanel from "./components/SettingsPanel.vue";
import { settings } from "./stores/settings";
import { inRoom, localPet, me, others, registerTap } from "./stores/room";
import {
  isTauri, listenInput, listenTray, resizeWindow, setAlwaysOnTop, setClickThrough, type InputEvent,
} from "./composables/tauri";

const panelOpen = ref(!isTauri); // in a plain browser, show the panel right away
const tab = ref<"room" | "settings">("room");
const root = ref<HTMLElement | null>(null);

// ---- local pet state, driven by the global input hook ----
const pet = reactive({ keyDown: false, left: false, right: false, dx: 0, dy: 0 });
let keysHeld = 0;
let velX = 0;
let velY = 0;
let raf = 0;

function onInput(e: InputEvent) {
  switch (e.kind) {
    case "key_down":
      keysHeld += 1;
      pet.keyDown = true;
      registerTap();
      break;
    case "key_up":
      keysHeld = Math.max(0, keysHeld - 1);
      pet.keyDown = keysHeld > 0;
      break;
    case "mouse_down":
      if (e.button === "left") pet.left = true;
      else if (e.button === "right") pet.right = true;
      registerTap();
      break;
    case "mouse_up":
      if (e.button === "left") pet.left = false;
      else if (e.button === "right") pet.right = false;
      break;
    case "mouse_move":
      if (!settings.mouseFollow) break;
      // Ignore teleports (e.g. monitor switch), smooth the rest.
      if (Math.hypot(e.dx, e.dy) > 100) break;
      velX += (e.dx * settings.mouseSensitivity - velX) * 0.3;
      velY += (e.dy * settings.mouseSensitivity - velY) * 0.3;
      break;
  }
}

// Mouse layer: integrate velocity, clamp, decay back to centre.
const MAX_OFF = 20;
const RETURN = 0.05;
function tick() {
  pet.dx = Math.max(-MAX_OFF, Math.min(MAX_OFF, (pet.dx + velX) * (1 - RETURN)));
  pet.dy = Math.max(-MAX_OFF, Math.min(MAX_OFF, (pet.dy + velY) * (1 - RETURN)));
  velX *= 0.7;
  velY *= 0.7;
  raf = requestAnimationFrame(tick);
}

let unInput: (() => void) | undefined;
let unTray: (() => void) | undefined;
let ro: ResizeObserver | undefined;

onMounted(async () => {
  unInput = await listenInput(onInput);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") panelOpen.value = !panelOpen.value;
    else settings.clickThrough = !settings.clickThrough;
  });
  raf = requestAnimationFrame(tick);
  if (root.value && isTauri) {
    ro = new ResizeObserver(() => {
      const r = root.value!.getBoundingClientRect();
      resizeWindow(Math.ceil(r.width), Math.ceil(r.height));
    });
    ro.observe(root.value);
  }
});
onBeforeUnmount(() => {
  unInput?.();
  unTray?.();
  ro?.disconnect();
  cancelAnimationFrame(raf);
});

watch(() => settings.clickThrough, (v) => setClickThrough(v), { immediate: true });
watch(() => settings.alwaysOnTop, (v) => setAlwaysOnTop(v), { immediate: true });

// While click-through is on the window can't receive clicks, so hide the panel.
watch(() => settings.clickThrough, (v) => v && (panelOpen.value = false));

const myCharacter = computed(() => settings.character);
const REMOTE_SCALE = 0.4;
const remoteCols = computed(() => Math.min(5, Math.max(1, others.value.length)));
</script>

<template>
  <div ref="root" class="root">
    <div class="stage">
      <PetView
        :character="myCharacter"
        :scale="settings.scale"
        :key-down="pet.keyDown"
        :mouse-dx="pet.dx"
        :mouse-dy="pet.dy"
        :left-down="pet.left"
        :right-down="pet.right"
        :emote="localPet.emote"
        :label="inRoom ? (me?.nick ?? '') : ''"
        draggable
      />
      <button v-if="!settings.clickThrough" class="gear" title="房间 / 设置" @click="panelOpen = !panelOpen">⚙</button>
    </div>

    <div v-if="others.length" class="remotes" :style="{ gridTemplateColumns: `repeat(${remoteCols}, auto)` }">
      <PetView
        v-for="m in others"
        :key="m.id"
        :character="m.character"
        :scale="REMOTE_SCALE"
        :pulse="m.pulse"
        :emote="m.emote"
        :bursts="m.bursts"
        :label="m.nick"
      />
    </div>

    <div v-if="panelOpen && !settings.clickThrough" class="panel">
      <div class="tabs">
        <button :class="{ on: tab === 'room' }" @click="tab = 'room'">房间</button>
        <button :class="{ on: tab === 'settings' }" @click="tab = 'settings'">设置</button>
      </div>
      <RoomPanel v-show="tab === 'room'" />
      <SettingsPanel v-show="tab === 'settings'" />
    </div>
  </div>
</template>

<style>
html, body, #app { margin: 0; background: transparent; overflow: hidden; font-family: "Microsoft YaHei", system-ui, sans-serif; }
</style>

<style scoped>
.root { display: inline-flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px; min-width: 300px; box-sizing: border-box; }
.stage { position: relative; }
.gear {
  position: absolute; right: -2px; top: -2px; width: 22px; height: 22px; border-radius: 50%; border: none; padding: 0;
  background: rgba(0, 0, 0, 0.45); color: #fff; cursor: pointer; opacity: 0; transition: opacity 120ms;
}
.stage:hover .gear { opacity: 1; }
.remotes { display: grid; gap: 4px 6px; justify-items: center; }
.panel {
  width: 300px; box-sizing: border-box; padding: 10px; border-radius: 12px; background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.3); color: #222;
}
.tabs { display: flex; gap: 4px; margin-bottom: 8px; }
.tabs button { flex: 1; padding: 4px; border: none; background: #f2f2f2; border-radius: 6px; cursor: pointer; font-size: 12px; }
.tabs button.on { background: #ff6b9d; color: #fff; }
</style>
