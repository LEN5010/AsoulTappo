<script setup lang="ts">
// The desk overlay holds the own pet and room members. Tauri opens the panel in a
// separate regular window; the browser preview keeps it inside the overlay.
// Only the drawn parts take the mouse (see hit.ts); everything else clicks through.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import PetActor from "./pet/PetActor.vue";
import PetView from "./pet/PetView.vue";
import CounterBar from "./pet/CounterBar.vue";
import QuickEmote from "./pet/QuickEmote.vue";
import CooldownBubble from "./pet/CooldownBubble.vue";
import AdminBubble from "./pet/AdminBubble.vue";
import DuelBubble from "./pet/DuelBubble.vue";
import DuelPick from "./pet/DuelPick.vue";
import {
  DUEL_HEIGHT, DUEL_WIDTH, bubblePlacement, closePick, insidePick, openPick, pickSize,
} from "./pet/duelPick";
import AccessBubble from "./pet/AccessBubble.vue";
import NamePill from "./pet/NamePill.vue";
import NamePlate from "./pet/NamePlate.vue";
import { getPlate, nameBand, plateSize } from "./pet/plates";
import { remotePetSize } from "./pet/bounds";
import MainPanel from "./panel/MainPanel.vue";
import { PET_BASE } from "./characters";
import { starterEmotesOf } from "./items";
import { characterColor } from "./manifest";
import { settings } from "./stores/settings";
import { counter, watchDay } from "./stores/counter";
import { onInput, pet, stopPet, tapCooldown } from "./stores/pet";
import { shardCombo } from "./stores/shardPop";
import { draws, online, startReporting, stopReporting } from "./stores/player";
import { inRoom, localPet, memberKey, others, roomId, sendEmote, shownNick, type RemoteMember } from "./stores/room";
import { startDebugLog } from "./debugLog";
import {
  clamp, defaultPetPos, dockY, enterRoom, nextSlot, placeOwn, placeRemote, remotePos, viewport, type Pos, type Size,
} from "./stores/desk";
import { openPanel, togglePanel, ui } from "./stores/ui";
import { updateBusy, updateDialogOpen, updateForced, updateOffer, updatePercent, watchRelease } from "./stores/update";
import { skinVars } from "./stores/theme";
import { startHitReporter } from "./hit";
import {
  debugLogEnabled, isTauri, listenInput, listenInputAccess, listenInputBlocked, listenOutsideClick, listenTray, setAlwaysOnTop, setBossKey, setClickThrough,
  setHitRegions, type InputBlocked,
} from "./composables/tauri";

// ---- viewport
const onResize = () => (viewport.value = { w: window.innerWidth, h: window.innerHeight });
onResize();

// ---- own pet
const ownSize = ref<Size>({ w: PET_BASE.width * settings.scale, h: PET_BASE.height * settings.scale + 30 });
/** The own pet's size with the strip under it, which a docked or folded pet does not have. */
const fullSize = ref<Size>({ ...ownSize.value });
/** While the own pet is dragged: whether it would dock where it is now. Null when it is not dragged. */
const dragDock = ref<boolean | null>(null);
const docked = computed(() => dragDock.value ?? settings.petDocked);
/** The strip stays under the pet: not folded away, and not on the bottom edge where it has no room. */
const barPinned = computed(() => !settings.barFolded && !docked.value);
/** A click on the pet shows an unpinned strip for a few seconds; a docked pet rises off the edge to make room. */
const peek = ref(false);
const PEEK_MS = 6000;
let peekTimer: ReturnType<typeof setTimeout> | undefined;
/** Restarts the countdown; the quick emotes hold the strip open while they are. */
function keepPeek() {
  clearTimeout(peekTimer);
  if (peek.value && !ui.quickOpen) peekTimer = setTimeout(() => (peek.value = false), PEEK_MS);
}
function onOwnTap() {
  if (barPinned.value || settings.clickThrough) return;
  peek.value = !peek.value;
}
const barShown = computed(() => !settings.clickThrough && (barPinned.value || peek.value));
const ownPos = computed<Pos>(() => {
  if (settings.petDocked) {
    const x = clamp({ x: settings.petX, y: 0 }, ownSize.value).x;
    return peek.value ? clamp({ x, y: dockY(settings.scale) }, fullSize.value) : { x, y: dockY(settings.scale) };
  }
  return settings.petX < 0 ? defaultPetPos(ownSize.value) : clamp({ x: settings.petX, y: settings.petY }, ownSize.value);
});
function placeOwnDrag(p: Pos): Pos {
  peek.value = false;
  const placed = placeOwn(p, fullSize.value, settings.scale);
  dragDock.value = placed.docked;
  return placed.pos;
}
function onOwnMoved(p: Pos) {
  settings.petDocked = dragDock.value ?? false;
  dragDock.value = null;
  settings.petX = p.x;
  settings.petY = p.y;
}
function onOwnSize(size: Size) {
  ownSize.value = size;
  if (barShown.value) fullSize.value = size;
}
function resetPet() {
  settings.petDocked = false;
  settings.petX = -1;
  settings.petY = -1;
}
/** The strip's last key: folds a pinned strip away, pins one shown by a click. A docked pet cannot pin it. */
function toggleFold() {
  settings.barFolded = !settings.barFolded;
  peek.value = false;
}
watch(barShown, (shown) => { if (!shown) ui.quickOpen = false; });
watch([peek, () => ui.quickOpen], keepPeek);
const barWidth = computed(() => Math.max(212, PET_BASE.width * settings.scale));
const shownCount = computed(() => (settings.tapView === "today" ? counter.today : counter.total));
const quickKeys = computed(() => (settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character)));

// ---- quick emotes
function pickQuick(key: string) {
  sendEmote(key);
}
function closeQuick(e: Event) {
  const t = e.target as HTMLElement | null;
  if (!t?.closest?.(".dock, .spark")) ui.quickOpen = false;
  if (!t?.closest?.("[data-own-pet]")) peek.value = false;
  // The duel key over a partner's pet closes on a press anywhere else; a click on a pet shows it again.
  if (!insidePick(e.target)) closePick();
}
const closeOnEscape = (e: KeyboardEvent) => { if (e.key === "Escape") closePick(); };

// ---- other members on the desk
/** Empty with partners hidden: nothing of them is rendered, so they take no clicks either. */
const shownOthers = computed(() => (settings.showPartners ? others.value : []));
const remotePlate = computed(() => plateSize(settings.remoteScale));
const remoteName = computed(() => nameBand(settings.remoteScale));
/** A partner's name plate, when they wear one and plates are shown. */
const plateOf = (m: RemoteMember) => (settings.showPlates ? getPlate(m.plate)?.id : undefined);
const remoteSize = computed<Size>(() => remotePetSize(settings.remoteScale, settings.showNames, settings.showPlates));
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
/** Where the duel bubbles go so they stay on screen: the key and the bets over a partner, the duel over the own pet. */
const pickPlace = (m: RemoteMember) => bubblePlacement(remoteAt(m), remoteSize.value, pickSize(), viewport.value);
const duelPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: DUEL_WIDTH, h: DUEL_HEIGHT }, viewport.value));
/** Bubbles grow to the left when there is no room on the right of the head (see PetView). */
const nearRight = (x: number, scale: number, minEmote: number) =>
  x + 172 * scale + Math.max(minEmote, 72 * scale) + 24 > viewport.value.w;

// ---- window, input and tray
let unInput: (() => void) | undefined;
let unTray: (() => void) | undefined;
let unOutside: (() => void) | undefined;
let hits: ReturnType<typeof startHitReporter> | undefined;
let stopDebugLog: (() => void) | undefined;
let unBlocked: (() => void) | undefined;
let stopDay: (() => void) | undefined;
let stopRelease: (() => void) | undefined;
// The desk window watches the server's minimum version itself; the panel, which holds the dialog, may never be opened.
watch(updateForced, (must) => { if (must) openPanel(); });
// Shown from the first time an elevated program kept the pet from hearing input, until closed.
const adminHint = ref<InputBlocked | null>(null);
let unAccess: (() => void) | undefined;
// macOS: shown while the hook lacks the input permission, until granted or closed.
const accessHint = ref(false);
const kick = () => hits?.kick();
/** A click on another window closes the quick emotes: blur where the overlay takes focus, outside-click on Windows where it never does. */
const closeQuickAway = () => {
  ui.quickOpen = false;
  peek.value = false;
  closePick();
};

onMounted(async () => {
  window.addEventListener("resize", onResize);
  window.addEventListener("pointerdown", closeQuick, true);
  window.addEventListener("blur", closeQuickAway);
  window.addEventListener("keydown", closeOnEscape);
  startReporting();
  stopDay = watchDay();
  if (isTauri) stopRelease = watchRelease();
  unInput = await listenInput(onInput);
  unOutside = await listenOutsideClick(closeQuickAway);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") togglePanel();
    else if (a === "open-panel") openPanel();
    else if (a === "reset-position") resetPet();
    else settings.clickThrough = !settings.clickThrough;
  });
  if (isTauri) hits = startHitReporter((rects, scale) => void setHitRegions(rects, scale));
  else document.documentElement.classList.add("browser-preview");
  unBlocked = await listenInputBlocked((b) => { if (b.by) adminHint.value = b; });
  unAccess = await listenInputAccess((missing) => (accessHint.value = missing));
  if (await debugLogEnabled()) {
    stopDebugLog = startDebugLog(() => `online ${online.value}, in room ${inRoom.value}, ` +
      `click-through ${settings.clickThrough}, always on top ${settings.alwaysOnTop}`);
  }
  // Dev-only look at the update dialog. Production builds drop this branch.
  if (import.meta.env.DEV && !isTauri && new URLSearchParams(location.search).get("preview") === "update") {
    const shot = new URLSearchParams(location.search).get("shot");
    updateOffer.value = {
      version: "0.1.0-beta.7",
      notes: "睡衣派对三款皮肤\n共鸣开包按抽取顺序揭晓",
    };
    updateDialogOpen.value = shot !== "row";
    if (shot === "progress") {
      updateBusy.value = true;
      updatePercent.value = 64;
    }
    openPanel("settings");
  }
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  window.removeEventListener("blur", closeQuickAway);
  window.removeEventListener("pointerdown", closeQuick, true);
  window.removeEventListener("keydown", closeOnEscape);
  stopReporting();
  unInput?.();
  unOutside?.();
  unTray?.();
  hits?.stop();
  stopDebugLog?.();
  unBlocked?.();
  stopDay?.();
  stopRelease?.();
  unAccess?.();
  stopPet();
});

watch(() => settings.clickThrough, (v) => setClickThrough(v), { immediate: true });
watch(() => settings.alwaysOnTop, (v) => setAlwaysOnTop(v), { immediate: true });
// The settings page reports a refused shortcut when it is recorded; at startup it is only in the log.
watch(() => settings.bossKey, (v) => void setBossKey(v).catch(() => {}), { immediate: true });
// While click-through is on the overlay can't receive clicks, so close what needs them.
watch(() => settings.clickThrough, (v) => {
  if (v) {
    ui.quickOpen = false;
  }
});
watch(() => [ui.panelOpen, ui.quickOpen, draws.value], kick, { flush: "post" });
</script>

<template>
  <div class="desk" :style="skinVars">
    <PetActor
      v-for="m in shownOthers" :key="m.id" :pos="remoteAt(m)" :label="shownNick(m)"
      @moved="(p) => placeRemote(memberKey(m), p)" @dragging="kick" @tap="openPick(m)"
    >
      <PetView
        :character="m.character" :scale="settings.remoteScale" :pulse="m.pulse"
        :key-down="m.motion.keyDown" :mouse-dx="m.motion.dx" :mouse-dy="m.motion.dy"
        :left-down="m.motion.left" :right-down="m.motion.right" smooth-mouse
        :emote="m.emote" :combo="m.combo" :win="m.win"
        :flip-bubble="nearRight(remoteAt(m).x, settings.remoteScale, 44)"
      />
      <template v-if="settings.showNames">
        <NamePlate
          v-if="plateOf(m)" :card="plateOf(m)!" :nick="shownNick(m)" :color="characterColor(m.character)"
          :width="remotePlate.width" :height="remotePlate.height" :font="remoteName.font"
        />
        <NamePill
          v-else :nick="shownNick(m)" :color="characterColor(m.character)" :width="PET_BASE.width * settings.remoteScale"
          :height="remoteName.pill" :font="remoteName.font"
        />
      </template>
      <DuelPick :id="m.id" v-bind="pickPlace(m)" />
    </PetActor>

    <PetActor
      :pos="ownPos" label="我的桌宠" :place="placeOwnDrag" glide data-own-pet
      @moved="onOwnMoved" @size="onOwnSize" @dragging="kick" @tap="onOwnTap" @pointermove="keepPeek"
    >
      <PetView
        :character="settings.character" :scale="settings.scale" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
        :left-down="pet.left" :right-down="pet.right"  :emote="localPet.emote" :combo="shardCombo" combo-icon="shard"
        :win="localPet.win"
        :min-emote="56" :flip-bubble="nearRight(ownPos.x, settings.scale, 56)"
      />
      <CooldownBubble :until="tapCooldown" />
      <AdminBubble v-if="adminHint" :hint="adminHint" @close="adminHint = null" />
      <DuelBubble v-bind="duelPlace" />
      <AccessBubble v-if="accessHint" @close="accessHint = false" />
      <CounterBar
        v-if="barShown" :count="shownCount" :view="settings.tapView" :width="barWidth" :quick-open="ui.quickOpen"
        :draws="draws"
        @toggle-view="settings.tapView = settings.tapView === 'today' ? 'total' : 'today'"
        @quick="ui.quickOpen = !ui.quickOpen" @menu="togglePanel" @resonance="openPanel('resonance')"
        :fold="docked ? undefined : barPinned ? 'fold' : 'pin'" @fold="toggleFold"
      >
        <QuickEmote v-if="ui.quickOpen" :keys="quickKeys" @pick="pickQuick" />
      </CounterBar>

    </PetActor>

    <Transition name="panel">
      <MainPanel v-if="!isTauri && ui.panelOpen" @reset-pet="resetPet" />
    </Transition>
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
.desk { position: fixed; inset: 0; pointer-events: none; }
.desk > :deep(*) { pointer-events: auto; }
</style>
