<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { settings } from "../stores/settings";
import { draws, online, shards, status } from "../stores/player";
import { incomeTip } from "../income";
import { inRoom, members } from "../stores/room";
import { reducedMotion, skinVars } from "../stores/theme";
import { clamp, viewport } from "../stores/desk";
import { closePanel, ui, type Page } from "../stores/ui";
import { isPanelWindow, setDragging } from "../composables/tauri";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Icon from "../ui/Icon.vue";
import { EASE_OUT, nextFrame, rise } from "../ui/motion";
import { useSlider } from "../ui/useSlider";
import PageShutter from "./PageShutter.vue";
import UpdateDialog from "./UpdateDialog.vue";
import AlpacaEasterEgg from "./AlpacaEasterEgg.vue";
import NoticeDialog from "./NoticeDialog.vue";
import { lookForUpdate, watchRelease } from "../stores/update";

// Every page is a chunk of its own. Opening the panel loads the page it opens on; a page turn loads its page
// behind the shutter, and the rest are fetched one by one once the first page is up (see warmPages).
const PAGES = {
  emotes: () => import("./EmotesPage.vue"),
  resonance: () => import("./ResonancePage.vue"),
  dex: () => import("./CollectionPage.vue"),
  checkin: () => import("./CheckinPage.vue"),
  scratch: () => import("./ScratchPage.vue"),
  room: () => import("./OnlinePage.vue"),
  settings: () => import("./SettingsPage.vue"),
} satisfies Record<Page, () => Promise<unknown>>;
const EmotesPage = defineAsyncComponent(PAGES.emotes);
const ResonancePage = defineAsyncComponent(PAGES.resonance);
const CollectionPage = defineAsyncComponent(PAGES.dex);
const CheckinPage = defineAsyncComponent(PAGES.checkin);
const ScratchPage = defineAsyncComponent(PAGES.scratch);
const OnlinePage = defineAsyncComponent(PAGES.room);
const SettingsPage = defineAsyncComponent(PAGES.settings);
/** Resolves once the page's code is in; a failed load is left for the page itself to show. */
const loadPage = (page: Page) => PAGES[page]().catch(() => {});
const WARM_STEP_MS = 400;
let warming: ReturnType<typeof setTimeout> | undefined;
function warmPages() {
  const rest = (Object.keys(PAGES) as Page[]).filter((page) => page !== shown.value);
  const next = () => {
    const page = rest.shift();
    if (!page) { warming = undefined; return; }
    void loadPage(page);
    warming = setTimeout(next, WARM_STEP_MS);
  };
  warming = setTimeout(next, WARM_STEP_MS);
}

const emit = defineEmits<{ resetPet: [] }>();
const NAV: { id: Page; label: string; en: string; icon: string }[] = [
  { id: "emotes", label: "背包", en: "BACKPACK", icon: "backpack" },
  { id: "resonance", label: "共鸣", en: "RESONANCE", icon: "card-spark" },
  { id: "dex", label: "图鉴", en: "CODEX", icon: "codex" },
  { id: "checkin", label: "签到", en: "CHECK-IN", icon: "calendar" },
  { id: "scratch", label: "刮刮乐", en: "SCRATCH", icon: "ticket" },
  { id: "room", label: "联机", en: "ONLINE", icon: "people" },
  { id: "settings", label: "设置", en: "SETTINGS", icon: "gear" },
];
/**
 * `dwell` keeps the covered shutter up so its title can be read; a slow mount eats into it.
 * `rise` starts the new page once the bands are on their way out.
 */
const OPEN_TIMING = { dwell: 180, rise: 150 };
const TURN_TIMING = { dwell: 50, rise: 80 };

const size = computed(() => isPanelWindow
  ? { w: viewport.value.w - 20, h: viewport.value.h - 20 }
  : { w: Math.min(980, viewport.value.w - 20), h: Math.min(700, viewport.value.h - 20) });
const pos = computed(() =>
  isPanelWindow ? { x: 10, y: 10 } : clamp(
    settings.panelX < 0
      ? { x: (viewport.value.w - size.value.w) / 2, y: (viewport.value.h - size.value.h) / 2 }
      : { x: settings.panelX, y: settings.panelY },
    size.value,
  ),
);
const live = ref<{ x: number; y: number } | null>(null);
let drag: { px: number; py: number; x: number; y: number; id: number } | null = null;

function down(e: PointerEvent) {
  if (e.button !== 0 || (e.target as HTMLElement).closest("button, input")) return;
  if (isPanelWindow) { void getCurrentWindow().startDragging(); return; }
  drag = { px: e.clientX, py: e.clientY, x: pos.value.x, y: pos.value.y, id: e.pointerId };
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  void setDragging(true);
}
function move(e: PointerEvent) {
  if (drag && e.pointerId === drag.id) {
    live.value = clamp({ x: drag.x + e.clientX - drag.px, y: drag.y + e.clientY - drag.py }, size.value);
  }
}
function up(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  drag = null;
  void setDragging(false);
  if (live.value) {
    settings.panelX = live.value.x;
    settings.panelY = live.value.y;
  }
  live.value = null;
}
// Escape closes the panel; digit keys pick a page in nav order. Both stand down while an overlay is open,
// and digits also while typing.
function onKey(e: KeyboardEvent) {
  if (document.querySelector("[data-overlay]")) return;
  if (e.key === "Escape") {
    closePanel();
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  const n = Number(e.key);
  if (!Number.isInteger(n) || n < 1 || n > NAV.length) return;
  if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]")) return;
  ui.page = NAV[n - 1]!.id;
}

// ---- page turns
// ui.page moves at once (the nav highlight follows it); the shown page swaps behind the
// shutter. Clicks that outrun the animation only ever leave the latest page pending.
const shown = ref<Page>(ui.page);
const nextNav = computed(() => NAV.find((n) => n.id === ui.page) ?? NAV[0]!);
const shutter = ref<InstanceType<typeof PageShutter>>();
const body = ref<HTMLElement>();
let turning = false;

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function settle(opening = false) {
  const { dwell, rise: riseDelay } = opening ? OPEN_TIMING : TURN_TIMING;
  for (;;) {
    const covered = performance.now();
    shown.value = ui.page;
    // The shutter stays down until the page's code is there, so it never lifts on an empty body.
    await loadPage(shown.value);
    await nextTick();
    await nextFrame();
    await pause(dwell - (performance.now() - covered));
    rise(body.value, body.value, riseDelay);
    if (!(await shutter.value?.reveal(opening))) return;
  }
}
async function turnPage() {
  if (turning) {
    if (ui.page !== shown.value) shutter.value?.rewind();
    return;
  }
  if (ui.page === shown.value) return;
  if (reducedMotion.value) {
    shown.value = ui.page;
    return;
  }
  turning = true;
  void loadPage(ui.page);
  await shutter.value?.cover();
  await settle();
  turning = false;
  if (ui.page !== shown.value) void turnPage();
}
watch(() => ui.page, turnPage);

// ---- opening: the nav keys light up top to bottom and the alpaca peeks out of the bottom edge
const deco = ref<InstanceType<typeof AlpacaEasterEgg>>();
const NAV_STEP_MS = 30;
function lightUp() {
  if (reducedMotion.value) return;
  navEl.value?.querySelectorAll<HTMLElement>("button").forEach((el, i) =>
    el.animate(
      [{ opacity: 0, transform: "translateX(-10px)" }, { opacity: 1, transform: "none" }],
      { duration: 320, delay: 90 + i * NAV_STEP_MS, easing: EASE_OUT, fill: "backwards" },
    ),
  );
  (deco.value?.$el as HTMLElement | undefined)?.animate(
    [{ transform: "translate(-50%, 60%)" }, { transform: "translate(-50%, -10%)" }],
    { duration: 520, delay: 240, easing: "cubic-bezier(0.34, 1.56, 0.64, 1)", fill: "backwards" },
  );
}
// Kept alive in the panel window: reopening activates it again rather than mounting it.
let activations = 0;
onActivated(() => {
  if (activations++ === 0) return;
  lightUp();
  // A minimum version or an announcement may have been set while the panel was closed.
  void lookForUpdate(false, true);
});
let stopRelease: (() => void) | undefined;
onBeforeUnmount(() => stopRelease?.());

onMounted(async () => {
  window.addEventListener("keydown", onKey);
  stopRelease = watchRelease();
  lightUp();
  if (reducedMotion.value) { warmPages(); return; }
  turning = true;
  shutter.value?.hold();
  await settle(true);
  turning = false;
  warmPages();
  if (ui.page !== shown.value) void turnPage();
});
onBeforeUnmount(() => {
  clearTimeout(warming);
  window.removeEventListener("keydown", onKey);
  if (drag) void setDragging(false);
});

const navEl = ref<HTMLElement>();
const navThumb = ref<HTMLElement>();
useSlider(navEl, navThumb, () => ui.page);

// ---- shard balance: rolls to each new value, flashing coral when it grows
const ROLL_MS = 400;
const shownShards = ref(shards.value);
const flash = ref(0);
let primed = status.value !== null;
let roll = 0;
watch(shards, (to, from) => {
  cancelAnimationFrame(roll);
  if (!primed || reducedMotion.value) {
    primed = true;
    shownShards.value = to;
    return;
  }
  if (to > from) flash.value++;
  const base = shownShards.value;
  const start = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / ROLL_MS);
    shownShards.value = Math.round(base + (to - base) * (1 - (1 - t) ** 3));
    if (t < 1) roll = requestAnimationFrame(step);
  };
  roll = requestAnimationFrame(step);
});
onBeforeUnmount(() => cancelAnimationFrame(roll));
const walletTip = computed(() => incomeTip(status.value));

function badgeOf(id: Page): number {
  if (id === "resonance") return draws.value;
  if (id === "checkin") return status.value?.checkin?.available ? 1 : 0;
  if (id === "room" && inRoom.value) return members.size;
  return 0;
}
</script>

<template>
  <section
    class="panel" data-hit role="dialog" aria-label="AsoulTappo 面板"
    :style="{
      ...skinVars, width: `${size.w}px`, height: `${size.h}px`, left: `${(live ?? pos).x}px`, top: `${(live ?? pos).y}px`,
    }"
  >
    <span class="glow" aria-hidden="true"></span>

    <div class="face">
      <div class="main">
        <div class="topbar" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up">
          <span v-if="!online" class="offline" role="status"><i aria-hidden="true"></i>未连接</span>
          <span class="wallet" :title="walletTip">
            <Icon name="shard" :size="16" />
            <b :key="flash" :class="{ gain: flash > 0 }">{{ shownShards.toLocaleString("en-US") }}</b>
          </span>
          <button v-if="isPanelWindow" type="button" class="win ui-btn ghost" title="最小化" aria-label="最小化" @click="getCurrentWindow().minimize()">
            <Icon name="minus" :size="16" />
          </button>
          <button type="button" class="win ui-btn ghost" title="关闭面板" aria-label="关闭面板" @click="closePanel">
            <Icon name="close" :size="16" />
          </button>
        </div>

        <main ref="body" class="body" :key="settings.serverUrl">
          <KeepAlive>
            <EmotesPage v-if="shown === 'emotes'" />
            <CollectionPage v-else-if="shown === 'dex'" />
            <CheckinPage v-else-if="shown === 'checkin'" />
            <ScratchPage v-else-if="shown === 'scratch'" />
            <ResonancePage v-else-if="shown === 'resonance'" />
            <OnlinePage v-else-if="shown === 'room'" class="form-page ui-scroll" />
            <SettingsPage v-else class="form-page ui-scroll" @reset-pet="emit('resetPet')" />
          </KeepAlive>
        </main>
      </div>

      <PageShutter ref="shutter" :title="nextNav.en" :label="nextNav.label" />

      <aside class="side">
        <div class="logo" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up">
          <span class="logo-mark" role="img" aria-label="A-SOUL"></span>
          <span class="logo-word">TAPPO</span>
        </div>

        <nav ref="navEl" aria-label="主导航">
          <i ref="navThumb" class="nav-thumb" aria-hidden="true"></i>
          <button
            v-for="(n, i) in NAV" :key="n.id" type="button"
            :class="{ on: ui.page === n.id }" :title="`${n.label}（${i + 1}）`"
            :aria-current="ui.page === n.id ? 'page' : undefined"
            @click="ui.page = n.id"
          >
            <span class="nav-face" aria-hidden="true"></span>
            <Icon class="nav-icon" :name="n.icon" :size="20" />
            <b class="nav-label">{{ n.label }}</b>
            <span v-if="badgeOf(n.id) > 0" class="pip">{{ badgeOf(n.id) }}</span>
          </button>
        </nav>

        <AlpacaEasterEgg ref="deco" class="side-deco" />
      </aside>

      <UpdateDialog />
      <NoticeDialog />
      <div class="panel-overlay"></div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  --side-w: 168px;
  position: absolute;
  z-index: 40;
  box-sizing: border-box;
  container: panel / size;
  font-family: var(--font);
  color: var(--ink);
}
.panel-enter-active {
  animation: panel-in var(--dur-slow) var(--ease-out);
}
.panel-leave-active {
  transition: opacity var(--dur-fast) var(--ease-in), transform var(--dur-fast) var(--ease-in);
}
.panel-leave-to {
  opacity: 0;
  transform: translate(16px, -10px);
}
@keyframes panel-in {
  from {
    opacity: 0;
    transform: translate(-24px, 16px);
  }
}

/* Depth comes from a static blur behind the face. */
.glow {
  position: absolute;
  inset: 24px 16px 10px 24px;
  background: rgba(var(--c-900-rgb), 0.42);
  filter: blur(24px);
  will-change: transform;
}
.face {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--surface);
  border-radius: var(--radius-l);
}

.main {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-50);
}
/* The drag handle: the shard balance and the window keys sit on its right. */
.topbar {
  position: relative;
  z-index: 3;
  height: 46px;
  flex: none;
  margin-left: var(--side-w);
  padding-right: 8px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  cursor: grab;
  user-select: none;
}
.topbar:active {
  cursor: grabbing;
}
.offline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 8px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--c-700);
}
.offline i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-700);
}
.wallet {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  margin-right: 6px;
  padding: 0 12px 0 10px;
  box-sizing: border-box;
  border-radius: var(--radius-key);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  color: var(--c-500);
  cursor: default;
}
.wallet b {
  min-width: 2ch;
  font: 800 18px/1 var(--font-latin);
  color: var(--ink);
}
.wallet b.gain {
  animation: shard-gain 600ms var(--ease-out);
}
@keyframes shard-gain {
  0%,
  30% {
    color: var(--c-600);
  }
}
.win {
  width: 32px;
  height: 32px;
  padding: 0;
}

.body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin-left: var(--side-w);
}
.form-page {
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  padding: 14px 20px 28px 16px;
}

/* Modals teleport here, so they sit above the sidebar and cover the whole face. */
.panel-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  pointer-events: none;
}
.panel-overlay > :deep(*) {
  pointer-events: auto;
}

/* Flat coral with a little light across the top. White focus rings on this ground. */
.side {
  --focus: #fff;
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 2;
  width: var(--side-w);
  /* The sticker crosses onto the page. The face still clips the panel edge; modals stay above this. */
  overflow: visible;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding-top: 22px;
  background: var(--grad-sky);
  user-select: none;
}

.logo {
  flex: none;
  width: 120px;
  margin-left: 22px;
  display: flex;
  flex-direction: column;
  cursor: grab;
}
.logo:active {
  cursor: grabbing;
}
.logo-mark {
  display: block;
  width: 100%;
  aspect-ratio: 3.172;
  background: #fff;
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
/* Right-aligned under the mark; the negative margin takes back the trailing letter-spacing. */
.logo-word {
  align-self: flex-end;
  margin: 5px -0.32em 0 0;
  font: 800 13px/1 var(--font-latin);
  letter-spacing: 0.32em;
  color: #fff;
}

nav {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 20px;
}
/* The selected page is a cream tab that runs off the sidebar's edge into the page, curving away above and below. */
.nav-thumb {
  --seam: 12px;
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  border-radius: var(--seam) 0 0 var(--seam);
  background: var(--c-50);
  transform-origin: 0 50%;
  will-change: transform;
}
.nav-thumb::before,
.nav-thumb::after {
  content: "";
  position: absolute;
  right: 0;
  width: var(--seam);
  height: var(--seam);
}
.nav-thumb::before {
  bottom: 100%;
  background: radial-gradient(circle at 0 0, transparent var(--seam), var(--c-50) calc(var(--seam) + 0.5px));
}
.nav-thumb::after {
  top: 100%;
  background: radial-gradient(circle at 0 100%, transparent var(--seam), var(--c-50) calc(var(--seam) + 0.5px));
}
nav button {
  position: relative;
  isolation: isolate;
  width: calc(100% - 12px);
  height: 44px;
  margin-left: 12px;
  flex: none;
  /* Right padding = face right inset + left padding, so the pip sits as far inside the face as the icon. */
  padding: 0 26px 0 14px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  background: none;
  color: #fff;
  font: inherit;
  cursor: pointer;
  transition: color var(--dur-base);
}
nav button:focus-visible {
  outline-offset: -3px;
}
nav button.on {
  --focus: var(--ink);
  color: var(--ink);
  cursor: default;
}
/* A low coral key: invisible at rest, its face comes up under the pointer and sinks when pressed.
 * Equal top and bottom insets keep the face centred on the content, which moves with it. */
.nav-face {
  position: absolute;
  inset: 5px 12px 5px 0;
  z-index: -1;
  border-radius: var(--radius-key);
  background: linear-gradient(180deg, color-mix(in oklab, var(--c-400) 70%, #fff), var(--c-400));
  box-shadow: 0 3px 0 var(--c-600), var(--shadow-key);
  opacity: 0;
  transform: translateY(3px);
  transition:
    opacity var(--dur-fast),
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring);
}
nav button:not(.on):hover .nav-face {
  opacity: 1;
  transform: translateY(-1px);
}
nav button:not(.on):active .nav-face {
  transform: translateY(2px);
  box-shadow: 0 0 0 var(--c-600), 0 1px 2px -1px rgba(var(--shadow-rgb), 0.2);
  transition-duration: var(--dur-press), var(--dur-press), var(--dur-press);
  transition-timing-function: ease-out;
}
.nav-icon,
.nav-label,
.pip {
  transition: transform var(--dur-release) var(--ease-spring);
}
nav button:not(.on):hover > :not(.nav-face) {
  transform: translateY(-1px);
}
nav button:not(.on):active > :not(.nav-face) {
  transform: translateY(2px);
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.nav-label {
  flex: 1;
  min-width: 0;
  text-align: left;
  font: 800 16px/1 var(--font);
  white-space: nowrap;
}
nav button.on .nav-label {
  color: var(--c-700);
}
.pip {
  flex: none;
  min-width: 22px;
  height: 18px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: 9px;
  background: #fff;
  color: var(--c-700);
  font: 800 var(--fs-body)/18px var(--font-latin);
  text-align: center;
}
nav button.on .pip {
  background: var(--c-500);
  color: var(--ink);
}
/* The alpaca and its surprise sticker peek up from the bottom edge. */
.side-deco {
  position: absolute;
  left: 50%;
  bottom: -46px;
  width: 104px;
  aspect-ratio: 420 / 620;
  transform: translate(-50%, -10%);
}

@container panel (max-width: 760px) {
  .face {
    --side-w: 140px;
  }
  .logo {
    width: 100px;
    margin-left: 18px;
  }
  .logo-word {
    font-size: var(--fs-label);
  }
  nav button {
    width: calc(100% - 8px);
    margin-left: 8px;
    gap: 8px;
    padding: 0 20px 0 10px;
  }
  .nav-face {
    right: 10px;
  }
  .side-deco {
    bottom: -40px;
    width: 96px;
  }
}
/* Below these heights the alpaca would run into the last nav item. */
@container panel (max-height: 600px) {
  .side-deco {
    bottom: -34px;
    width: 84px;
  }
}
@container panel (max-height: 500px) {
  .side-deco {
    display: none;
  }
}
</style>
