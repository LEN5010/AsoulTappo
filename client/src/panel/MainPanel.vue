<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { settings } from "../stores/settings";
import { boxes, online, tickets } from "../stores/player";
import { inRoom, members } from "../stores/room";
import { reducedMotion, skinVars } from "../stores/theme";
import { clamp, viewport } from "../stores/desk";
import { ui, type Page } from "../stores/ui";
import { setDragging } from "../composables/tauri";
import Icon from "../ui/Icon.vue";
import { EASE_OUT, nextFrame, rise, SLANT } from "../ui/motion";
import { useSlider } from "../ui/useSlider";
import CollectionPage from "./CollectionPage.vue";
import CardsPage from "./CardsPage.vue";
import EmotesPage from "./EmotesPage.vue";
import OnlinePage from "./OnlinePage.vue";
import PageShutter from "./PageShutter.vue";
import SettingsPage from "./SettingsPage.vue";

const emit = defineEmits<{ resetPet: [] }>();
const NAV: { id: Page; label: string; en: string; icon: string }[] = [
  { id: "emotes", label: "背包", en: "BACKPACK", icon: "bag" },
  { id: "dex", label: "图鉴", en: "CODEX", icon: "book" },
  { id: "cards", label: "收藏集", en: "COLLECTION", icon: "card" },
  { id: "room", label: "联机", en: "ONLINE", icon: "users" },
  { id: "settings", label: "设置", en: "SETTINGS", icon: "nut" },
];
const BACK_OFFSET = 6;
const NAV_STEP = 54;
/** How far the collapsed sidebar slides under the panel edge. */
const SIDE_TRAVEL = 44;
/**
 * `dwell` keeps the covered shutter up so its title can be read; a slow mount eats into it.
 * `rise` starts the new page once the bands are on their way out.
 */
const OPEN_TIMING = { dwell: 180, rise: 150 };
const TURN_TIMING = { dwell: 50, rise: 80 };

const size = computed(() => ({ w: Math.min(980, viewport.value.w - 20), h: Math.min(700, viewport.value.h - 20) }));
const pos = computed(() =>
  clamp(
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
  if (e.key === "Escape" && !document.querySelector("[data-overlay]")) ui.panelOpen = false;
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

function toggleSidebar() {
  settings.sidebarCollapsed = !settings.sidebarCollapsed;
  if (reducedMotion.value) return;
  const from = settings.sidebarCollapsed ? SIDE_TRAVEL : -SIDE_TRAVEL;
  body.value?.animate([{ transform: `translateX(${from}px)` }, { transform: "none" }], { duration: 340, easing: EASE_OUT });
}

function badgeOf(id: Page): number {
  if (id === "dex") return boxes.value;
  if (id === "cards") return tickets.value;
  if (id === "room" && inRoom.value) return members.size;
  return 0;
}
</script>

<template>
  <section
    class="panel" data-hit role="dialog" aria-label="AsoulTappo 面板"
    :style="{
      ...skinVars, width: `${size.w}px`, height: `${size.h}px`, left: `${(live ?? pos).x}px`, top: `${(live ?? pos).y}px`,
      '--back': `${BACK_OFFSET}px`, '--side-run': `${(size.h - BACK_OFFSET) * SLANT}px`, '--side-travel': `${SIDE_TRAVEL}px`,
    }"
  >
    <span class="glow" aria-hidden="true"></span>
    <span class="back" aria-hidden="true"></span>

    <div class="face" :class="{ mini: settings.sidebarCollapsed }">
      <div class="main">
        <span class="wedge" aria-hidden="true"></span>

        <div class="topbar" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
          <h1 class="page-title">{{ shownNav.label }}<em>{{ shownNav.en }}</em></h1>
          <span v-if="!online" class="offline ui-tag dark" role="status"><i aria-hidden="true"></i>未连接</span>
          <span class="ticks" aria-hidden="true"><i></i><i></i><i></i></span>
          <button type="button" class="close ui-slant" title="关闭面板" aria-label="关闭面板" @click="ui.panelOpen = false">
            <Icon name="close" :size="15" />
          </button>
        </div>

        <main ref="body" class="body" :key="settings.serverUrl">
          <KeepAlive>
            <EmotesPage v-if="shown === 'emotes'" />
            <CollectionPage v-else-if="shown === 'dex'" />
            <CardsPage v-else-if="shown === 'cards'" />
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
            <span class="logo-word lbl ui-slant">TAPPO</span>
          </div>

          <nav ref="navEl" aria-label="主导航">
            <i ref="navThumb" class="nav-thumb" aria-hidden="true"></i>
            <button
              v-for="(n, i) in NAV" :key="n.id" type="button"
              :class="{ on: ui.page === n.id }" :title="n.label"
              :style="{ marginLeft: `${30 - i * NAV_STEP * SLANT}px` }"
              :aria-current="ui.page === n.id ? 'page' : undefined"
              @click="ui.page = n.id"
            >
              <span class="nav-icon"><Icon :name="n.icon" :size="20" /></span>
              <span class="lbl nav-text"><b>{{ n.label }}</b><small>{{ n.en }}</small></span>
              <span v-if="badgeOf(n.id) > 0" class="pip" :class="{ soft: n.id === 'room' }">{{ badgeOf(n.id) }}</span>
            </button>
          </nav>

          <span class="side-deco lbl" aria-hidden="true"></span>

          <button
            type="button" class="fold"
            :title="settings.sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
            @click="toggleSidebar"
          >
            <Icon :name="settings.sidebarCollapsed ? 'unfold' : 'fold'" :size="19" />
            <span class="lbl">收起</span>
          </button>
        </div>
      </aside>

      <div class="panel-overlay"></div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  --side-w: 196px;
  --panel-cut: var(--cut-l);
  --panel-clip: polygon(
    var(--panel-cut) 0, 100% 0, 100% calc(100% - var(--panel-cut)),
    calc(100% - var(--panel-cut)) 100%, 0 100%, 0 var(--panel-cut)
  );
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

/* clip-path drops box-shadow, so depth comes from a static blur and an offset block behind the face */
.glow {
  position: absolute;
  inset: 24px 16px 10px 24px;
  background: rgba(var(--ink-rgb), 0.42);
  filter: blur(24px);
  will-change: transform;
}
.back {
  position: absolute;
  inset: var(--back) 0 0 var(--back);
  background: var(--accent);
  clip-path: var(--panel-clip);
}
.face {
  position: absolute;
  inset: 0 var(--back) var(--back) 0;
  overflow: hidden;
  background: var(--surface);
  clip-path: var(--panel-clip);
}

.main {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: flex;
  flex-direction: column;
  background: var(--page);
}
/* Fills the blank wedge under the sidebar's slanted edge. */
.wedge {
  position: absolute;
  z-index: -1;
  left: 112px;
  bottom: 16px;
  width: 72px;
  height: 52px;
  background: repeating-linear-gradient(90deg, rgba(var(--accent-rgb), 0.45) 0 6px, transparent 6px 14px);
  transform: skewX(var(--skew));
  transition: left var(--dur-slow) var(--ease-out);
}
.mini .wedge {
  left: calc(112px - var(--side-travel));
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
  font: 400 var(--fs-title)/1 var(--font-display);
  color: var(--ink);
}
.page-title em {
  font: italic 800 var(--fs-strong)/1 var(--font-latin);
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
  transform: skewX(var(--skew));
}
.ticks {
  display: flex;
  gap: 5px;
  height: 14px;
  margin-right: 12px;
  transform: skewX(var(--skew));
}
.ticks i {
  width: 5px;
  background: var(--accent);
}
.close {
  --slant-bg: var(--ink);
  width: 52px;
  height: 26px;
  margin-right: 10px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--on-ink);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.close:hover {
  --slant-bg: var(--accent-deep);
}

.body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin-left: var(--side-w);
}
.mini .body,
.mini .topbar {
  margin-left: calc(var(--side-w) - var(--side-travel));
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

/* The outer shape is the pale edge strip; the orange fill sits inside it along the same slant. */
.side {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 2;
  width: var(--side-w);
  background: var(--accent-soft);
  clip-path: polygon(0 0, 100% 0, calc(100% - var(--side-run)) 100%, 0 100%);
  user-select: none;
  transition: transform var(--dur-slow) var(--ease-out);
}
.side-fill {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--accent);
  clip-path: polygon(0 0, calc(100% - 12px) 0, calc(100% - 12px - var(--side-run)) 100%, 0 100%);
}
.side-inner {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 0 12px;
  box-sizing: border-box;
  transition: transform var(--dur-slow) var(--ease-out);
}
/* Collapsing only moves layers: the orange edge slides left while the icons hold still. */
.mini .side {
  transform: translateX(calc(var(--side-travel) * -1));
}
.mini .side-inner {
  transform: translateX(var(--side-travel));
}
.lbl {
  transition: opacity var(--dur-base);
}
.side-deco {
  position: absolute;
  left: 12px;
  bottom: 60px;
  width: 82px;
  aspect-ratio: 122 / 152;
  background: var(--on-ink);
  pointer-events: none;
  mask: url("../assets/brand/side-cat.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/side-cat.svg") center / contain no-repeat;
}
/* Below this height the mascot would run into the last nav item. */
@container panel (max-height: 550px) {
  .side-deco {
    display: none;
  }
}
.mini .lbl {
  opacity: 0;
  pointer-events: none;
}

.logo {
  position: relative;
  height: 84px;
  flex: none;
  padding-left: 14px;
  cursor: grab;
}
.logo:active {
  cursor: grabbing;
}
.logo-mark {
  display: block;
  width: 146px;
  aspect-ratio: 3.172;
  background: var(--surface);
  transform-origin: 0 0;
  transition: transform var(--dur-slow) var(--ease-out);
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.mini .logo-mark {
  transform: translateX(2px) scale(0.78);
}
.logo-word.ui-slant {
  position: absolute;
  left: 68px;
  top: 52px;
  padding: 0 10px 0 12px;
  font: italic 800 var(--fs-section)/22px var(--font-latin);
  letter-spacing: 0.22em;
  color: var(--on-ink);
  --slant-bg: var(--ink);
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
  background: var(--surface);
  transform-origin: 0 50%;
  will-change: transform;
}
.nav-thumb::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  background: var(--ink);
}
nav button {
  position: relative;
  width: 214px;
  height: 46px;
  flex: none;
  padding: 0 0 0 16px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 0;
  background: none;
  color: var(--on-accent);
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
  background: var(--surface);
  color: var(--accent-deep);
  transform: skewX(var(--skew));
  transform-origin: 0 50%;
  transition: background var(--dur-base), color var(--dur-base), transform var(--dur-slow) var(--ease-out);
}
.nav-icon .icon {
  stroke-width: 2.4;
  transform: skewX(calc(var(--skew) * -1));
}
.mini .nav-icon {
  transform: skewX(var(--skew)) scale(1.16);
}
.fold .icon {
  transform-origin: 0 50%;
  transition: transform var(--dur-slow) var(--ease-out);
}
.mini .fold .icon {
  transform: scale(1.3);
}
nav button.on {
  color: var(--accent-deep);
}
nav button.on .nav-icon {
  background: var(--accent);
  color: var(--on-accent);
}
.nav-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
}
.nav-text b {
  font: var(--fs-heading)/1 var(--font-display);
}
.nav-text small {
  font: italic 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.1em;
  color: var(--on-accent);
  transition: color var(--dur-base);
}
nav button.on .nav-text small {
  color: inherit;
}
/* Pinned to the icon tile: the slanted edge leaves no room beside the longer labels. */
.pip {
  position: absolute;
  left: 44px;
  top: 0;
  min-width: 20px;
  height: 18px;
  padding: 0 4px;
  box-sizing: border-box;
  background: var(--ink);
  color: var(--on-ink);
  font: italic 800 var(--fs-body)/18px var(--font-latin);
  text-align: center;
  transform: skewX(var(--skew));
}
.pip.soft {
  background: var(--accent-deep);
}
.mini .pip {
  left: 50px;
}

.fold {
  margin: auto 0 0 14px;
  width: 72px;
  height: 34px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--on-accent);
  font: 800 var(--fs-strong) var(--font);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out);
}
.fold:hover {
  transform: translateX(3px);
}
/* the slanted edge is narrowest down here, so the hit area must shrink to the icon */
.mini .fold {
  width: 30px;
}
</style>
