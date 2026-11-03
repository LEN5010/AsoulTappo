<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import PetView from "./components/PetView.vue";
import RoomPanel from "./components/RoomPanel.vue";
import CollectionPanel from "./components/CollectionPanel.vue";
import ThemePanel from "./components/ThemePanel.vue";
import ProfilePanel from "./components/ProfilePanel.vue";
import { MouseMotion } from "./MouseMotion";
import { settings } from "./stores/settings";
import { countInput, startReporting, stopReporting, boxes } from "./stores/player";
import { backgroundFor, cssImage } from "./skin";
import { skin, skinVars } from "./stores/theme";
import { inRoom, localPet, me, others, registerTap } from "./stores/room";
import {
  isTauri, listenInput, listenTray, resizeWindow, setAlwaysOnTop, setClickThrough, type InputEvent,
} from "./composables/tauri";

const panelOpen = ref(!isTauri); // in a plain browser, show the panel right away
type Tab = "main" | "channel" | "dynamic" | "myself";
const tab = ref<Tab>("main");
const TABS: { id: Tab; label: string }[] = [
  { id: "main", label: "房间" },
  { id: "channel", label: "图鉴" },
  { id: "dynamic", label: "主题" },
  { id: "myself", label: "我的" },
];
const tabIdx = computed(() => TABS.findIndex((t) => t.id === tab.value));
const panelStyle = computed(() => ({
  ...skinVars.value,
  "--bg-img": cssImage(backgroundFor(skin.value, tabIdx.value)),
  "--head-img": cssImage(skin.value.headBg),
  "--tab-img": cssImage(skin.value.tabBg),
}));
const root = ref<HTMLElement | null>(null);

// ---- local pet state, driven by the global input hook ----
const pet = reactive({ keyDown: false, left: false, right: false, dx: 0, dy: 0 });
let keysHeld = 0;
const motion = new MouseMotion(pet);

function onInput(e: InputEvent) {
  switch (e.kind) {
    case "key_down":
      keysHeld += 1;
      pet.keyDown = true;
      registerTap();
      countInput();
      break;
    case "key_up":
      keysHeld = Math.max(0, keysHeld - 1);
      pet.keyDown = keysHeld > 0;
      break;
    case "mouse_down":
      if (e.button === "left") pet.left = true;
      else if (e.button === "right") pet.right = true;
      registerTap();
      countInput();
      break;
    case "mouse_up":
      if (e.button === "left") pet.left = false;
      else if (e.button === "right") pet.right = false;
      break;
    case "mouse_move":
      if (!settings.mouseFollow) break;
      motion.move(e.dx, e.dy, settings.mouseSensitivity);
      break;
  }
}

watch(() => settings.mouseFollow, (enabled) => { if (!enabled) motion.stop(); }, { flush: "sync" });

let unInput: (() => void) | undefined;
let unTray: (() => void) | undefined;
let ro: ResizeObserver | undefined;

onMounted(async () => {
  startReporting();
  unInput = await listenInput(onInput);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") panelOpen.value = !panelOpen.value;
    else settings.clickThrough = !settings.clickThrough;
  });
  if (root.value && isTauri) {
    ro = new ResizeObserver(() => {
      const r = root.value!.getBoundingClientRect();
      resizeWindow(Math.ceil(r.width), Math.ceil(r.height));
    });
    ro.observe(root.value);
  }
});
onBeforeUnmount(() => {
  stopReporting();
  unInput?.();
  unTray?.();
  ro?.disconnect();
  motion.stop();
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

    <div v-if="panelOpen && !settings.clickThrough" class="panel" :style="panelStyle">
      <header class="head">
        <strong>AsoulTappo</strong>
        <span v-if="boxes" class="boxes" title="可开启的宝箱">🎁 {{ boxes }}</span>
      </header>
      <main class="content" role="tabpanel">
        <RoomPanel v-show="tab === 'main'" />
        <CollectionPanel v-if="tab === 'channel'" :key="settings.serverUrl" />
        <ThemePanel v-show="tab === 'dynamic'" />
        <ProfilePanel v-if="tab === 'myself'" />
      </main>
      <nav class="tabs" role="tablist" aria-label="面板">
        <button
          v-for="t in TABS" :key="t.id" role="tab" :aria-selected="tab === t.id" :class="{ on: tab === t.id }" @click="tab = t.id"
        >
          <img v-if="skin.icons[t.id]" :src="tab === t.id ? skin.icons[t.id].s : skin.icons[t.id].n" alt="" draggable="false" />
          <span>{{ t.label }}</span>
        </button>
      </nav>
    </div>
  </div>
</template>

<style>
html, body, #app { margin: 0; background: transparent; overflow: hidden; font-family: "Microsoft YaHei", system-ui, sans-serif; }
/* shared form controls (theme colors come from CSS variables set on .panel) */
.panel button, .panel input, .panel select { font-family: inherit; font-size: 12px; }
.panel input:not([type="checkbox"]):not([type="range"]), .panel select {
  padding: 5px 8px; border: 1px solid rgba(0, 0, 0, 0.18); border-radius: 8px; background: rgba(255, 255, 255, 0.75); color: inherit;
}
.panel button {
  padding: 5px 10px; border-radius: 8px; border: 1px solid rgba(0, 0, 0, 0.15); background: rgba(255, 255, 255, 0.8); color: inherit; cursor: pointer;
}
.panel button.primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
.panel button:disabled { opacity: 0.5; cursor: default; }
.panel input[type="range"], .panel input[type="checkbox"] { accent-color: var(--accent); }
.panel :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; scroll-behavior: auto !important; }
}
</style>

<style scoped>
.root { display: inline-flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px; min-width: 300px; box-sizing: border-box; }
.stage { position: relative; }
.gear {
  position: absolute; right: -2px; top: -2px; width: 22px; height: 22px; border-radius: 50%; border: none; padding: 0;
  background: rgba(0, 0, 0, 0.45); color: #fff; cursor: pointer; opacity: 0; transition: opacity 120ms;
}
.stage:hover .gear, .gear:focus-visible { opacity: 1; }
.remotes { display: grid; gap: 4px 6px; justify-items: center; }
.panel {
  width: 300px; box-sizing: border-box; border-radius: 16px; overflow: hidden; color: #2b2326; display: flex; flex-direction: column;
  background: var(--bg-img) center / cover, linear-gradient(160deg, var(--tint), #fff);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(var(--accent-rgb), 0.35);
}
.head {
  display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; min-height: 30px; font-size: 13px;
  background: var(--head-img) center / cover, linear-gradient(90deg, var(--accent), var(--char));
  color: var(--head-fg); text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}
.boxes { font-size: 12px; background: rgba(0, 0, 0, 0.35); color: #fff; padding: 1px 8px; border-radius: 999px; }
.content {
  margin: 8px; padding: 10px; border-radius: 12px; max-height: 420px; overflow-y: auto; scrollbar-width: thin;
  background: rgba(255, 255, 255, 0.78); backdrop-filter: blur(8px) saturate(1.2);
  border: 1px solid rgba(255, 255, 255, 0.7);
}
.tabs {
  display: flex; background: var(--tab-img) center / cover, rgba(255, 255, 255, 0.9);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}
.tabs button {
  flex: 1; padding: 5px 0 4px; border: none; background: none; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 1px;
  font-size: 10px; color: var(--tab-fg); opacity: 0.8;
}
.tabs button img { width: 26px; height: 26px; object-fit: contain; }
.tabs button.on { opacity: 1; font-weight: 800; text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 2px; text-decoration-color: var(--accent); }
.tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: -3px; }
</style>
