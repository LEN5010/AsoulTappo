<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { settings } from "../stores/settings";
import { draws, online } from "../stores/player";
import { inRoom, members } from "../stores/room";
import { reducedMotion, skinVars } from "../stores/theme";
import { clamp, viewport } from "../stores/desk";
import { closePanel, ui, type Page } from "../stores/ui";
import { isPanelWindow, setDragging } from "../composables/tauri";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Icon from "../ui/Icon.vue";
import { nextFrame, rise } from "../ui/motion";
import { useSlider } from "../ui/useSlider";
import CollectionPage from "./CollectionPage.vue";
import ResonancePage from "./ResonancePage.vue";
import EmotesPage from "./EmotesPage.vue";
import OnlinePage from "./OnlinePage.vue";
import PageShutter from "./PageShutter.vue";
import SettingsPage from "./SettingsPage.vue";
import AlpacaEasterEgg from "./AlpacaEasterEgg.vue";
import SideDesk from "./SideDesk.vue";

const emit = defineEmits<{ resetPet: [] }>();
const NAV: { id: Page; label: string; en: string; icon: string }[] = [
  { id: "emotes", label: "背包", en: "BACKPACK", icon: "bag" },
  { id: "resonance", label: "共鸣", en: "RESONANCE", icon: "card" },
  { id: "dex", label: "图鉴", en: "CODEX", icon: "book" },
  { id: "room", label: "联机", en: "ONLINE", icon: "users" },
  { id: "settings", label: "设置", en: "SETTINGS", icon: "nut" },
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
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && !document.querySelector("[data-overlay]")) closePanel();
}

// ---- page turns
// ui.page moves at once (the nav highlight follows it); the shown page swaps behind the
// shutter. Clicks that outrun the animation only ever leave the latest page pending.
const shown = ref<Page>(ui.page);
const shownNav = computed(() => NAV.find((n) => n.id === shown.value) ?? NAV[0]!);
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
  await shutter.value?.cover();
  await settle();
  turning = false;
  if (ui.page !== shown.value) void turnPage();
}
watch(() => ui.page, turnPage);

onMounted(async () => {
  window.addEventListener("keydown", onKey);
  if (reducedMotion.value) return;
  turning = true;
  shutter.value?.hold();
  await settle(true);
  turning = false;
  if (ui.page !== shown.value) void turnPage();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  if (drag) void setDragging(false);
});

const navEl = ref<HTMLElement>();
const navThumb = ref<HTMLElement>();
useSlider(navEl, navThumb, () => ui.page);

function badgeOf(id: Page): number {
  if (id === "resonance") return draws.value;
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
        <div class="topbar" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
          <h1 class="page-title">{{ shownNav.label }}<em>{{ shownNav.en }}</em></h1>
          <span v-if="!online" class="offline ui-tag dark" role="status"><i aria-hidden="true"></i>未连接</span>
          <button v-if="isPanelWindow" type="button" class="close ui-plate" title="最小化" aria-label="最小化" @click="getCurrentWindow().minimize()">
            <Icon name="minus" :size="15" />
          </button>
          <button type="button" class="close ui-plate" title="关闭面板" aria-label="关闭面板" @click="closePanel">
            <Icon name="close" :size="15" />
          </button>
        </div>

        <main ref="body" class="body" :key="settings.serverUrl">
          <KeepAlive>
            <EmotesPage v-if="shown === 'emotes'" />
            <CollectionPage v-else-if="shown === 'dex'" />
            <ResonancePage v-else-if="shown === 'resonance'" />
            <OnlinePage v-else-if="shown === 'room'" class="form-page ui-scroll" />
            <SettingsPage v-else class="form-page ui-scroll" @reset-pet="emit('resetPet')" />
          </KeepAlive>
        </main>
      </div>

      <PageShutter ref="shutter" :title="nextNav.en" :label="nextNav.label" />

      <aside class="side">
        <span class="side-fill" aria-hidden="true"></span>

        <div class="side-inner">
          <div class="logo" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
            <span class="logo-mark" role="img" aria-label="A-SOUL"></span>
            <span class="logo-word ui-plate">TAPPO</span>
          </div>

          <nav ref="navEl" aria-label="主导航">
            <i ref="navThumb" class="nav-thumb" aria-hidden="true"></i>
            <button
              v-for="n in NAV" :key="n.id" type="button"
              :class="{ on: ui.page === n.id }" :title="n.label"
              :aria-current="ui.page === n.id ? 'page' : undefined"
              @click="ui.page = n.id"
            >
              <span class="nav-icon"><Icon :name="n.icon" :size="20" /></span>
              <span class="nav-text"><b>{{ n.label }}</b><small>{{ n.en }}</small></span>
              <span v-if="badgeOf(n.id) > 0" class="pip" :class="{ soft: n.id === 'room' }">{{ badgeOf(n.id) }}</span>
            </button>
          </nav>

          <SideDesk class="side-desk" />

          <AlpacaEasterEgg class="side-deco" />
        </div>
      </aside>

      <div class="panel-overlay"></div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  --side-w: 196px;
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
  background: rgba(var(--ink-rgb), 0.42);
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
  background: var(--page);
}
.topbar {
  position: relative;
  z-index: 3;
  height: 46px;
  flex: none;
  margin-left: var(--side-w);
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  cursor: grab;
  user-select: none;
}
.topbar:active {
  cursor: grabbing;
}
.topbar::after {
  content: "";
  position: absolute;
  left: 16px;
  right: 20px;
  bottom: 0;
  height: 2px;
  background: var(--line-2);
}
.page-title {
  align-self: center;
  display: flex;
  align-items: baseline;
  gap: 9px;
  margin: 0 auto 0 16px;
  font: 800 var(--fs-title)/1 var(--font);
  color: var(--ink);
}
.page-title em {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  letter-spacing: 0.1em;
  color: var(--accent-deep);
}
.offline {
  align-self: center;
  margin-right: 14px;
  padding: 0 9px 0 7px;
  line-height: 20px;
}
.offline i {
  display: inline-block;
  width: 4px;
  height: 10px;
  margin-right: 5px;
  background: var(--bad);
}
.close {
  --plate-bg: transparent;
  width: 34px;
  height: 30px;
  margin: 8px 8px 0 0;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ink-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color var(--dur-fast);
}
.close:hover {
  --plate-bg: var(--accent-soft);
  color: var(--ink);
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

/* The outer shape is the pale edge strip; the orange fill sits inside it. */
.side {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 2;
  width: var(--side-w);
  overflow: hidden;
  background: var(--accent-soft);
  user-select: none;
}
.side-fill {
  position: absolute;
  inset: 0 12px 0 0;
  background: var(--grad-sky);
}
.side-inner {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 0 12px;
  box-sizing: border-box;
}

.logo {
  position: relative;
  width: 146px;
  height: 84px;
  flex: none;
  margin-left: 14px;
  filter: var(--contour) drop-shadow(0 2px 3px rgba(var(--ink-rgb), 0.22));
  cursor: grab;
}
.logo:active {
  cursor: grabbing;
}
.logo-mark {
  display: block;
  width: 146px;
  aspect-ratio: 3.172;
  background: var(--ink);
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.logo-word.ui-plate {
  position: absolute;
  right: 0;
  top: 52px;
  padding: 0 10px 0 12px;
  font: 800 var(--fs-section)/22px var(--font-latin);
  letter-spacing: 0.22em;
  color: var(--on-ink);
  --plate-bg: var(--ink);
}

nav {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.nav-thumb {
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  border-radius: var(--radius-m) 0 0 var(--radius-m);
  background: var(--surface);
  box-shadow: 0 6px 16px -8px rgba(var(--ink-rgb), 0.34);
  transform-origin: 0 50%;
  will-change: transform;
}
.nav-thumb::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 4px;
  border-radius: 2px;
  background: var(--grad-main);
}
nav button {
  position: relative;
  width: calc(100% - 14px);
  height: 46px;
  margin-left: 14px;
  flex: none;
  padding: 0 0 0 16px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 0;
  background: none;
  color: var(--on-accent-surface);
  cursor: pointer;
  transition: color var(--dur-base), transform var(--dur-base) var(--ease-out);
}
nav button:hover:not(.on) {
  transform: translateX(4px);
}
nav button:focus-visible {
  outline: none;
}
nav button:focus-visible .nav-icon {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}
.nav-icon {
  flex: none;
  width: 38px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-s);
  background: var(--surface);
  color: var(--accent-deep);
  transition: color var(--dur-base), box-shadow var(--dur-base);
}
nav button:hover:not(.on) .nav-icon {
  box-shadow: 0 0 12px rgba(255, 255, 255, 0.7);
}
.nav-icon .icon {
  stroke-width: 2.4;
}
nav button.on {
  color: var(--accent-deep);
}
nav button.on .nav-icon {
  background: var(--grad-main);
  box-shadow: var(--glow-s);
  color: var(--on-accent);
}
.nav-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
}
.nav-text b {
  font: 800 var(--fs-heading)/1 var(--font);
}
.nav-text small {
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.1em;
  color: var(--on-accent-surface);
  transition: color var(--dur-base);
}
nav button.on .nav-text small {
  color: inherit;
}
/* At the end of the row, clear of the label and of the 12px pale strip on the sidebar's right edge, even at three digits. */
.pip {
  position: absolute;
  right: 18px;
  top: 50%;
  min-width: 22px;
  height: 18px;
  padding: 0 5px;
  box-sizing: border-box;
  border-radius: 9px;
  transform: translateY(-50%);
  background: var(--ink);
  color: var(--on-ink);
  font: 800 var(--fs-body)/18px var(--font-latin);
  text-align: center;
}
.pip.soft {
  background: var(--accent-deep);
}
/* Under the nav, with headroom for the bust standing out of its top edge. */
.side-desk {
  flex: none;
  margin: 40px 26px 0 14px;
}
/* The alpaca and its surprise sticker share the bottom corner. */
.side-deco {
  position: absolute;
  left: 16px;
  bottom: -30px;
  width: 112px;
  aspect-ratio: 420 / 620;
}

@container panel (max-width: 760px) {
  .face {
    --side-w: 176px;
  }
  .logo {
    width: 128px;
    height: 74px;
    margin-left: 16px;
  }
  .logo-mark {
    width: 128px;
  }
  .logo-word.ui-plate {
    top: 45px;
    font-size: var(--fs-number);
    line-height: 19px;
  }
  nav button {
    width: calc(100% - 10px);
    margin-left: 10px;
    gap: 9px;
    padding-left: 10px;
  }
  .nav-text small {
    display: none;
  }
  .pip {
    right: 16px;
  }
  .side-deco {
    left: 14px;
    bottom: -24px;
    width: 92px;
  }
}
/* Below these heights the alpaca would run into the last nav item. */
@container panel (max-height: 600px) {
  .side-deco {
    left: 14px;
    bottom: -22px;
    width: 84px;
  }
}
@container panel (max-height: 500px) {
  .side-deco {
    display: none;
  }
}
/* Below this the card would crowd the alpaca. */
@container panel (max-height: 640px) {
  .side-desk {
    display: none;
  }
}
</style>
