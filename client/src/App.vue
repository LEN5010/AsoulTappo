<script setup lang="ts">
// The desk overlay holds the own pet and room members. Tauri opens the panel in a
// separate regular window; the browser preview keeps it inside the overlay.
// Only the drawn parts take the mouse (see hit.ts); everything else clicks through.
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from "vue";
import PetActor from "./pet/PetActor.vue";
import PetView from "./pet/PetView.vue";
import CounterBar from "./pet/CounterBar.vue";
import QuickEmote from "./pet/QuickEmote.vue";
import CooldownBubble from "./pet/CooldownBubble.vue";
import AdminBubble from "./pet/AdminBubble.vue";
import DuelBubble from "./pet/DuelBubble.vue";
import PokeBubble from "./pet/PokeBubble.vue";
import DuelPick from "./pet/DuelPick.vue";
import {
  DUEL_HEIGHT, DUEL_WIDTH, POKED_HEIGHT, POKED_WIDTH, bubblePlacement, closePick, insidePick, openPick, pickSize,
} from "./pet/duelPick";
import AccessBubble from "./pet/AccessBubble.vue";
import NamePill from "./pet/NamePill.vue";
import NamePlate from "./pet/NamePlate.vue";
import { getPlate, nameBand, plateSize } from "./pet/plates";
import { remotePetSize } from "./pet/bounds";
const MainPanel = defineAsyncComponent(() => import("./panel/MainPanel.vue"));
import { PET_BASE } from "./characters";
import { starterEmotesOf } from "./items";
import { characterColor } from "./manifest";
import { settings } from "./stores/settings";
import { counter, followServer, watchDay } from "./stores/counter";
import { onInput, pet, stopPet, tapCooldown } from "./stores/pet";
import { shardCombo } from "./stores/shardPop";
import { draws, online, startReporting, status, stopReporting } from "./stores/player";
import { duel, inRoom, localPet, memberKey, others, roomId, sendEmote, shownNick, type RemoteMember } from "./stores/room";
import { startDebugLog } from "./debugLog";
import { startCapture } from "./desktop/capture";
import {
  DESK_GAP, clamp, defaultPetPos, dockY, enterRoom, nextDockSlot, nextSlot, placePet, placeRemote, remotePos, viewport,
  type Pos, type Size,
} from "./stores/desk";
import { openPanel, togglePanel, ui } from "./stores/ui";
import { agreed } from "./legal/consent";
import { updateBusy, updateDialogOpen, updateForced, updateOffer, updatePercent, watchRelease } from "./stores/update";
import { skinVars } from "./stores/theme";
import { startHitReporter } from "./hit";
import {
  debugLogEnabled, isTauri, listenInput, listenInputAccess, listenInputBlocked, listenOutsideClick, listenTray, setAlwaysOnTop, setClickThrough, setHotkey,
  setHitRegions, type InputBlocked,
} from "./composables/tauri";

// ---- viewport
const onResize = () => (viewport.value = { w: window.innerWidth, h: window.innerHeight });
onResize();

// ---- own pet
const barWidth = computed(() => Math.max(212, PET_BASE.width * settings.scale));
/** Room on each side of the own name plate for its handle (`.own-plate` padding). */
const PLATE_GRIP = 14;
/**
 * The own pet's width, the same whether the strip, the name plate or nothing is under it. The pet stands centred in
 * it and the actor is placed by its left edge, so a width that followed what is under the pet would move the pet
 * when the strip folds, click-through hides it, or the handle swaps in the plate.
 */
const ownWidth = computed(() =>
  Math.max(barWidth.value, settings.gripPlate ? Math.round(PET_BASE.width * settings.scale) + PLATE_GRIP * 2 : 0));
const ownSize = ref<Size>({ w: PET_BASE.width * settings.scale, h: PET_BASE.height * settings.scale + 30 });
/** Height of the strip under the pet, measured while it shows. */
const stripHeight = ref(36);
/** The own pet's size with the strip under it, which a docked or folded pet does not have. */
const fullSize = computed<Size>(() => ({
  w: Math.max(ownSize.value.w, barWidth.value),
  h: Math.round(PET_BASE.height * settings.scale) + stripHeight.value,
}));
/** While the own pet is dragged: whether it would dock where it is now. Null when it is not dragged. */
const dragDock = ref<boolean | null>(null);
const docked = computed(() => dragDock.value ?? settings.petDocked);
/** The strip stays under the pet: not folded away in the settings, and not on the bottom edge where it has no room. */
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
  // Room for the strip is kept under the pet also while the strip is away, so a click can always show it.
  const size = { w: ownSize.value.w, h: Math.max(ownSize.value.h, fullSize.value.h) };
  return settings.petX < 0 ? defaultPetPos(size) : clamp({ x: settings.petX, y: settings.petY }, size);
});
function placeOwnDrag(p: Pos): Pos {
  peek.value = false;
  const placed = placePet(p, fullSize.value, settings.scale);
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
  const strip = size.h - Math.round(PET_BASE.height * settings.scale);
  // The plate is lower than the strip; the room kept under the pet stays the strip's, so the pet does not rise.
  if (barShown.value && !plateShown.value && strip > 0 && strip < 80) stripHeight.value = strip;
}
function resetPet() {
  settings.petDocked = false;
  settings.petX = -1;
  settings.petY = -1;
}
/** The strip's handle: tucks a pinned strip away, pins one a click brought out. A docked pet cannot pin it. */
function toggleFold() {
  settings.barFolded = !settings.barFolded;
  peek.value = false;
}
// With gripPlate the handle's click swaps the strip for the own name plate and back, and a double click does what
// a click does without it. A click waits this long for a second one.
const DOUBLE_CLICK_MS = 280;
let gripClick: ReturnType<typeof setTimeout> | undefined;
function onGrip() {
  if (!settings.gripPlate) return toggleFold();
  if (gripClick) {
    clearTimeout(gripClick);
    gripClick = undefined;
    toggleFold();
    return;
  }
  gripClick = setTimeout(() => {
    gripClick = undefined;
    settings.barPlate = !settings.barPlate;
    keepPeek();
  }, DOUBLE_CLICK_MS);
}
/** The own name plate in the strip's place, as partners see it under this pet; a docked pet keeps the strip. */
const plateShown = computed(() => settings.gripPlate && settings.barPlate && !docked.value);
const ownPlate = computed(() => getPlate(settings.plate)?.id);
const ownPlateSize = computed(() => plateSize(settings.scale));
const ownName = computed(() => nameBand(settings.scale));
const ownNick = computed(() => settings.nick.trim() || settings.character);
watch(barShown, (shown) => { if (!shown) ui.quickOpen = false; });
watch([peek, () => ui.quickOpen], keepPeek);
// Daily tap statistics and the local counter use the same China calendar day.
watch(() => [status.value?.totals.taps, status.value?.dailyTaps] as const, ([total, daily]) => {
  if (typeof total !== "number") return;
  followServer(total, daily);
}, { immediate: true });
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
      // Next to a docked own pet newcomers stand on the edge too, while it has room.
      const edge = settings.petDocked ? nextDockSlot(ownPos.value, ownSize.value, remoteSize.value, taken) : null;
      remotePos.set(key, edge ?? nextSlot(ownPos.value, ownSize.value, remoteSize.value, taken));
    }
  },
  { immediate: true },
);
const remoteDocked = (m: RemoteMember) => !!remotePos.get(memberKey(m))?.docked;
const remoteAt = (m: RemoteMember): Pos => {
  const p = remotePos.get(memberKey(m)) ?? ownPos.value;
  const at = clamp(p, remoteSize.value);
  return remoteDocked(m) ? { x: at.x, y: dockY(settings.remoteScale) } : at;
};
/** A partner docks on the bottom edge like the own pet. */
const placeRemoteDrag = (p: Pos) => placePet(p, remoteSize.value, settings.remoteScale).pos;
function onRemoteMoved(m: RemoteMember, p: Pos) {
  const placed = placePet(p, remoteSize.value, settings.remoteScale);
  placeRemote(memberKey(m), placed.docked ? { ...placed.pos, docked: true } : placed.pos);
}
/** A docked partner's name has no room under the desk; it goes over the desk's front instead. */
const nameOnDesk = (m: RemoteMember) =>
  remoteDocked(m) ? { position: "absolute" as const, bottom: `${Math.round(DESK_GAP * settings.remoteScale) + 4}px` } : undefined;
/** Where the duel bubbles go so they stay on screen: the key and the bets over a partner, the duel over the own pet. */
const pickPlace = (m: RemoteMember) => bubblePlacement(remoteAt(m), remoteSize.value, pickSize(), viewport.value);
const duelPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: DUEL_WIDTH, h: DUEL_HEIGHT }, viewport.value));
const pokedPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: POKED_WIDTH, h: POKED_HEIGHT }, viewport.value));
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
let stopCapture: (() => void) | undefined;
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
  // Reporting and the release watch wait for the terms; the panel holds the dialog that asks for them.
  startReporting();
  if (!agreed.value) openPanel();
  stopDay = watchDay();
  if (isTauri) stopRelease = watchRelease();
  unInput = await listenInput(onInput);
  unOutside = await listenOutsideClick(closeQuickAway);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") togglePanel();
    else if (a === "open-panel") openPanel();
    else if (a === "reset-position") resetPet();
    else if (a === "toggle-capture") settings.captureOpen = !settings.captureOpen;
    else settings.clickThrough = !settings.clickThrough;
  });
  if (isTauri) hits = startHitReporter((rects, scale) => void setHitRegions(rects, scale));
  else document.documentElement.classList.add("browser-preview");
  unBlocked = await listenInputBlocked((b) => { if (b.by) adminHint.value = b; });
  unAccess = await listenInputAccess((missing) => (accessHint.value = missing));
  if (isTauri) stopCapture = await startCapture();
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
  stopCapture?.();
  unAccess?.();
  stopPet();
});

watch(() => settings.clickThrough, (v) => setClickThrough(v), { immediate: true });
watch(() => settings.alwaysOnTop, (v) => setAlwaysOnTop(v), { immediate: true });
// The settings page reports a refused shortcut when it is recorded; at startup it is only in the log.
watch(() => settings.bossKey, (v) => void setHotkey("hide", v).catch(() => {}), { immediate: true });
watch(() => settings.clickThroughKey, (v) => void setHotkey("click-through", v).catch(() => {}), { immediate: true });
// While click-through is on the overlay can't receive clicks, so close what needs them.
watch(() => settings.clickThrough, (v) => {
  if (v) {
    ui.quickOpen = false;
  }
});
watch(() => [ui.panelOpen, ui.quickOpen, draws.value], kick, { flush: "post" });
</script>

<template>
  <div class="desk" :style="skinVars" @dragstart.prevent>
    <PetActor
      v-for="m in shownOthers" :key="m.id" :pos="remoteAt(m)" :label="shownNick(m)"
      :place="placeRemoteDrag" @moved="(p) => onRemoteMoved(m, p)" @dragging="kick" @tap="openPick(m)"
    >
      <PetView
        :character="m.character" :scale="settings.remoteScale" :pulse="m.pulse"
        :motion-id="m.id"
        :emote="m.emote" :combo="m.combo" :win="m.win"
        :flip-bubble="nearRight(remoteAt(m).x, settings.remoteScale, 44)"
      />
      <template v-if="settings.showNames">
        <NamePlate
          v-if="plateOf(m)" :card="plateOf(m)!" :nick="shownNick(m)" :color="characterColor(m.character)"
          :width="remotePlate.width" :height="remotePlate.height" :font="remoteName.font" :style="nameOnDesk(m)"
        />
        <NamePill
          v-else :nick="shownNick(m)" :color="characterColor(m.character)" :width="PET_BASE.width * settings.remoteScale"
          :height="remoteName.pill" :font="remoteName.font" :style="nameOnDesk(m)"
        />
      </template>
      <DuelPick :id="m.id" v-bind="pickPlace(m)" />
    </PetActor>

    <PetActor
      :pos="ownPos" label="我的桌宠" :place="placeOwnDrag" glide data-own-pet :style="{ width: `${ownWidth}px` }"
      @moved="onOwnMoved" @size="onOwnSize" @dragging="kick" @tap="onOwnTap" @pointermove="keepPeek"
    >
      <PetView
        :character="settings.character" :scale="settings.scale" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
        :left-down="pet.left" :right-down="pet.right"  :emote="localPet.emote" :combo="shardCombo" combo-icon="shard"
        :win="localPet.win" :pulse="localPet.pulse"
        :min-emote="56" :flip-bubble="nearRight(ownPos.x, settings.scale, 56)"
      />
      <CooldownBubble :until="tapCooldown" />
      <AdminBubble v-if="adminHint" :hint="adminHint" @close="adminHint = null" />
      <DuelBubble v-bind="duelPlace" />
      <PokeBubble v-if="!duel" v-bind="pokedPlace" />
      <AccessBubble v-if="accessHint" @close="accessHint = false" />
      <Transition name="strip" mode="out-in">
      <div v-if="barShown && plateShown" key="plate" class="own-plate">
        <NamePlate
          v-if="ownPlate" :card="ownPlate" :nick="ownNick" :color="characterColor(settings.character)"
          :width="ownPlateSize.width" :height="ownPlateSize.height" :font="ownName.font"
        />
        <NamePill
          v-else :nick="ownNick" :color="characterColor(settings.character)" :width="PET_BASE.width * settings.scale"
          :height="ownName.pill" :font="ownName.font"
        />
        <button
          type="button" class="plate-grip" aria-label="换回任务栏" @click="onGrip"
        ></button>
      </div>
      <CounterBar
        v-else-if="barShown" key="bar" :count="shownCount" :view="settings.tapView" :width="barWidth"
        :quick-open="ui.quickOpen" :draws="draws"
        @toggle-view="settings.tapView = settings.tapView === 'today' ? 'total' : 'today'"
        @quick="ui.quickOpen = !ui.quickOpen" @menu="togglePanel" @resonance="openPanel('resonance')"
        :grip="docked ? undefined : barPinned ? 'fold' : 'pin'" @grip="onGrip"
      >
        <QuickEmote v-if="ui.quickOpen" :keys="quickKeys" @pick="pickQuick" />
      </CounterBar>
      </Transition>

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
/* Nothing on the desk is selectable or draggable by the webview itself (template: dragstart), so pets leave no
   selection box or drag picture behind. */
.desk { position: fixed; inset: 0; pointer-events: none; -webkit-user-select: none; user-select: none; }
/* The strip comes out from under the desk and goes back there. It keeps its place in the layout while leaving. */
.strip-enter-active { transition: opacity var(--dur-base) var(--ease-out), translate var(--dur-slow) var(--ease-spring); }
.strip-leave-active { transition: opacity var(--dur-fast) var(--ease-in), translate var(--dur-release) var(--ease-in); }
.strip-enter-from, .strip-leave-to { opacity: 0; translate: 0 -14px; }
@media (prefers-reduced-motion: reduce) {
  .strip-enter-active, .strip-leave-active { transition: none; }
}
.desk > :deep(*) { pointer-events: auto; }
/* The own name plate in the strip's place, the handle on its left like the strip's: a short white line that reads
 * on any wallpaper. The side padding keeps the plate centred under the pet. */
.own-plate {
  position: relative;
  display: flex;
  padding: 2px 14px 0;
}
.plate-grip {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 14px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
}
.plate-grip::before {
  content: "";
  position: absolute;
  left: 5px;
  top: 50%;
  width: 4px;
  height: 14px;
  translate: 0 -50%;
  border-radius: 2px;
  background: var(--surface);
  box-shadow: 0 1px 3px rgba(var(--shadow-rgb), 0.45);
  transition: background var(--dur-fast), height var(--dur-fast) var(--ease-out);
}
.plate-grip:hover::before { height: 20px; background: var(--c-500); }
</style>
