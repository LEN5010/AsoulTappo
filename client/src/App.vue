<script setup lang="ts">
// The desk overlay: one transparent always-on-top window over the work area that holds
// the own pet (with its counter bar), the pets of everyone in the room and the panel.
// Only the drawn parts take the mouse (see hit.ts); everything else clicks through.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import PetActor from "./pet/PetActor.vue";
import PetView from "./pet/PetView.vue";
import CounterBar from "./pet/CounterBar.vue";
import ChestBubble from "./pet/ChestBubble.vue";
import QuickEmote from "./pet/QuickEmote.vue";
import DropToast from "./pet/DropToast.vue";
import NamePill from "./pet/NamePill.vue";
import MainPanel from "./panel/MainPanel.vue";
import { PET_BASE } from "./characters";
import { starterEmotesOf } from "./items";
import type { Drop } from "./net/api";
import { settings } from "./stores/settings";
import { counter } from "./stores/counter";
import { onInput, pet, stopPet } from "./stores/pet";
import { boxes, tickets, online, openBoxes, startReporting, stopReporting } from "./stores/player";
import { localPet, memberKey, others, roomId, sendEmote, type RemoteMember } from "./stores/room";
import {
  clamp, defaultPetPos, enterRoom, nextSlot, placeRemote, remotePos, viewport, type Pos, type Size,
} from "./stores/desk";
import { openPanel, togglePanel, ui } from "./stores/ui";
import { skinVars } from "./stores/theme";
import { startHitReporter } from "./hit";
import {
  isTauri, listenInput, listenTray, setAlwaysOnTop, setClickThrough, setHitRegions,
} from "./composables/tauri";

// ---- viewport
const onResize = () => (viewport.value = { w: window.innerWidth, h: window.innerHeight });
onResize();

// ---- own pet
const ownSize = ref<Size>({ w: PET_BASE.width * settings.scale, h: PET_BASE.height * settings.scale + 30 });
const ownPos = computed<Pos>(() =>
  settings.petX < 0 ? defaultPetPos(ownSize.value) : clamp({ x: settings.petX, y: settings.petY }, ownSize.value),
);
function onOwnMoved(p: Pos) {
  settings.petX = p.x;
  settings.petY = p.y;
}
function resetPet() {
  settings.petX = -1;
  settings.petY = -1;
}
const barWidth = computed(() => Math.max(212, PET_BASE.width * settings.scale));
const shownCount = computed(() => (settings.tapView === "today" ? counter.today : counter.total));
const quickKeys = computed(() => (settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character)));

// ---- chest and drops
const opening = ref(false);
const toasts = ref<Drop[]>([]);
async function openChest() {
  if (opening.value) return;
  opening.value = true;
  const drops = await openBoxes(1);
  opening.value = false;
  if (drops) toasts.value.push(...drops);
  else if (!online.value) openPanel("emotes");
}

// ---- quick emotes
function pickQuick(key: string) {
  sendEmote(key);
}
function closeQuick(e: Event) {
  const t = e.target as HTMLElement | null;
  if (!t?.closest?.(".dock, .spark")) ui.quickOpen = false;
}

// ---- other members on the desk
const remoteSize = computed<Size>(() => ({
  w: Math.max(PET_BASE.width * settings.remoteScale, 64),
  h: PET_BASE.height * settings.remoteScale + (settings.showNames ? 22 : 0),
}));
watch(roomId, (r) => enterRoom(r), { immediate: true });
// also re-runs when positions are forgotten (enterRoom / tidyRemotes) with the same members
watch(
  () => [others.value.map(memberKey), remotePos.size] as const,
  ([keys]) => {
    for (const key of keys) {
      if (remotePos.has(key)) continue;
      const taken = keys.map((k) => remotePos.get(k)).filter((p): p is Pos => !!p);
      remotePos.set(key, nextSlot(ownPos.value, ownSize.value, remoteSize.value, taken));
    }
  },
  { immediate: true },
);
const remoteAt = (m: RemoteMember) => clamp(remotePos.get(memberKey(m)) ?? ownPos.value, remoteSize.value);
/** Bubbles grow to the left when there is no room on the right of the head (see PetView). */
const nearRight = (x: number, scale: number, minEmote: number) =>
  x + 172 * scale + Math.max(minEmote, 72 * scale) + 24 > viewport.value.w;

// ---- window, input and tray
let unInput: (() => void) | undefined;
let unTray: (() => void) | undefined;
let hits: ReturnType<typeof startHitReporter> | undefined;
const kick = () => hits?.kick();

onMounted(async () => {
  window.addEventListener("resize", onResize);
  window.addEventListener("pointerdown", closeQuick, true);
  window.addEventListener("blur", () => (ui.quickOpen = false));
  startReporting();
  unInput = await listenInput(onInput);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") togglePanel();
    else if (a === "reset-position") resetPet();
    else settings.clickThrough = !settings.clickThrough;
  });
  if (isTauri) hits = startHitReporter((rects) => void setHitRegions(rects));
  else document.documentElement.classList.add("browser-preview");
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  window.removeEventListener("pointerdown", closeQuick, true);
  stopReporting();
  unInput?.();
  unTray?.();
  hits?.stop();
  stopPet();
});

watch(() => settings.clickThrough, (v) => setClickThrough(v), { immediate: true });
watch(() => settings.alwaysOnTop, (v) => setAlwaysOnTop(v), { immediate: true });
// While click-through is on the overlay can't receive clicks, so close what needs them.
watch(() => settings.clickThrough, (v) => {
  if (v) {
    ui.panelOpen = false;
    ui.quickOpen = false;
  }
});
watch(() => [ui.panelOpen, ui.quickOpen, toasts.value.length, boxes.value], kick, { flush: "post" });
</script>

<template>
  <div class="desk" :style="skinVars">
    <PetActor
      v-for="m in others" :key="m.id" :pos="remoteAt(m)" :label="m.nick"
      @moved="(p) => placeRemote(memberKey(m), p)" @dragging="kick"
    >
      <PetView
        :character="m.character" :scale="settings.remoteScale" :pulse="m.pulse"
        :emote="m.emote" :combo="m.combo" :flip-bubble="nearRight(remoteAt(m).x, settings.remoteScale, 44)"
      />
      <NamePill v-if="settings.showNames" :nick="m.nick" :width="Math.max(120, PET_BASE.width * settings.remoteScale)" />
    </PetActor>

    <PetActor :pos="ownPos" label="我的桌宠" @moved="onOwnMoved" @size="(s) => (ownSize = s)" @dragging="kick">
      <PetView
        :character="settings.character" :scale="settings.scale" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
        :left-down="pet.left" :right-down="pet.right"  :emote="localPet.emote"
        :min-emote="56" :flip-bubble="nearRight(ownPos.x, settings.scale, 56)"
      />
      <CounterBar
        v-if="!settings.clickThrough" :count="shownCount" :view="settings.tapView" :width="barWidth" :quick-open="ui.quickOpen"
        @toggle-view="settings.tapView = settings.tapView === 'today' ? 'total' : 'today'"
        @quick="ui.quickOpen = !ui.quickOpen" @menu="togglePanel"
      >
        <button v-if="tickets > 0" class="ticket-bubble" data-hit data-no-drag @click="openPanel('cards')">抽卡 ×{{ tickets }}</button>
        <ChestBubble v-if="boxes > 0" :count="boxes" :busy="opening" @open="openChest" />
        <QuickEmote v-if="ui.quickOpen" :keys="quickKeys" @pick="pickQuick" />
      </CounterBar>
      <DropToast v-if="!settings.clickThrough" :drop="toasts[0] ?? null" @done="toasts.shift()" />
    </PetActor>

    <MainPanel v-if="ui.panelOpen && !settings.clickThrough" @reset-pet="resetPet" />
  </div>
</template>

<style>
html, body, #app { margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }
body { font-family: var(--font); color: var(--ink); -webkit-font-smoothing: antialiased; }
/* plain browser preview (npm run dev): show a desktop-like background behind the overlay */
html.browser-preview body {
  background: radial-gradient(1200px 600px at 20% 10%, #cfe0f5, transparent), radial-gradient(900px 600px at 90% 90%, #f3d7e3, transparent), #dfe6ef;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; scroll-behavior: auto !important; }
}
</style>

<style scoped>
.ticket-bubble {
  position: absolute;
  left: 4px;
  bottom: calc(100% + 6px);
  border: 2px solid var(--accent-deep);
  border-radius: 999px;
  background: linear-gradient(180deg, #FFB596, var(--accent));
  box-shadow: 0 2.5px 0 var(--accent-deep);
  color: var(--on-accent);
  padding: 4px 12px;
  font: 800 12px var(--font);
  cursor: pointer;
  transition: transform 120ms;
}
.ticket-bubble:hover {
  transform: translateY(-2px);
}
.desk { position: fixed; inset: 0; pointer-events: none; }
.desk > :deep(*) { pointer-events: auto; }
</style>
