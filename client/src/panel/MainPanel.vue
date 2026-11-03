<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { settings } from "../stores/settings";
import { boxes, tickets } from "../stores/player";
import { inRoom, members } from "../stores/room";
import { skinVars } from "../stores/theme";
import { clamp, viewport } from "../stores/desk";
import { ui, type Page } from "../stores/ui";
import { setDragging } from "../composables/tauri";
import Icon from "../ui/Icon.vue";
import CollectionPage from "./CollectionPage.vue";
import EmotesPage from "./EmotesPage.vue";
import OnlinePage from "./OnlinePage.vue";
import SettingsPage from "./SettingsPage.vue";

const emit = defineEmits<{ resetPet: [] }>();
const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "emotes", label: "背包", icon: "bag" },
  { id: "dex", label: "图鉴", icon: "book" },
  { id: "room", label: "联机", icon: "home" },
  { id: "settings", label: "设置", icon: "nut" },
];

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
  if (e.key === "Escape" && !document.querySelector(".backdrop")) ui.panelOpen = false;
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  if (drag) void setDragging(false);
});

function badgeOf(id: Page): number {
  if (id === "emotes") return boxes.value;
  if (id === "dex") return tickets.value;
  if (id === "room" && inRoom.value) return members.size;
  return 0;
}
</script>

<template>
  <section
    class="panel" data-hit role="dialog" aria-label="AsoulTappo 面板"
    :style="{ ...skinVars, width: `${size.w}px`, height: `${size.h}px`, left: `${(live ?? pos).x}px`, top: `${(live ?? pos).y}px` }"
  >
    <aside class="side" :class="{ mini: settings.sidebarCollapsed }">
      <div class="logo" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
        <template v-if="!settings.sidebarCollapsed">
          <span class="logo-line top">Asoul</span>
          <span class="logo-line bot">
            Tappo
            <svg class="sparks" viewBox="0 0 24 28" width="18" height="22" aria-hidden="true">
              <ellipse cx="7" cy="6" rx="2.5" ry="4.5" transform="rotate(35 7 6)" fill="#FC966E" />
              <ellipse cx="14" cy="14" rx="2.5" ry="5" transform="rotate(68 14 14)" fill="#FFE0A3" />
              <ellipse cx="10" cy="22" rx="2.2" ry="4" transform="rotate(105 10 22)" fill="#FC966E" />
            </svg>
          </span>
        </template>
        <span v-else class="logo-mini">A✦</span>
      </div>

      <nav aria-label="主导航">
        <button
          v-for="n in NAV" :key="n.id" type="button"
          :class="{ on: ui.page === n.id }" :title="n.label"
          :aria-current="ui.page === n.id ? 'page' : undefined"
          @click="ui.page = n.id"
        >
          <Icon :name="n.icon" :size="22" />
          <span class="lbl">{{ n.label }}</span>
          <span v-if="badgeOf(n.id) > 0" class="pip" :class="{ soft: n.id === 'room' }">{{ badgeOf(n.id) }}</span>
        </button>
      </nav>

      <button
        type="button" class="fold"
        :title="settings.sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
        @click="settings.sidebarCollapsed = !settings.sidebarCollapsed"
      >
        <Icon :name="settings.sidebarCollapsed ? 'unfold' : 'fold'" :size="20" />
        <span class="lbl">收起</span>
      </button>
    </aside>

    <div class="main">
      <div class="awning" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
        <svg class="wave" viewBox="0 0 120 14" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 0 H120 V6 Q90 14 60 6 T0 6 Z" fill="#F3E2CE" />
          <path d="M0 6 Q30 -2 60 6 T120 6" fill="none" stroke="#E8D3BC" stroke-width="1.5" />
        </svg>
      </div>

      <button type="button" class="close-diamond" title="关闭面板" aria-label="关闭面板" @click="ui.panelOpen = false">
        <span class="diamond-rim">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M12 3l2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3z" fill="currentColor" />
          </svg>
        </span>
      </button>

      <main class="body" :key="settings.serverUrl">
        <KeepAlive>
          <EmotesPage v-if="ui.page === 'emotes'" />
          <CollectionPage v-else-if="ui.page === 'dex'" />
          <OnlinePage v-else-if="ui.page === 'room'" class="form-page ui-scroll" />
          <SettingsPage v-else class="form-page ui-scroll" @reset-pet="emit('resetPet')" />
        </KeepAlive>
      </main>
    </div>
  </section>
</template>

<style scoped>
.panel {
  position: absolute;
  z-index: 40;
  display: flex;
  overflow: hidden;
  box-sizing: border-box;
  border-radius: 26px;
  background: var(--paper);
  border: 3px solid #7E4529;
  box-shadow: 0 24px 60px rgba(60, 28, 12, 0.34), 0 4px 14px rgba(60, 28, 12, 0.18);
  font-family: var(--font);
  color: var(--ink);
  animation: open 180ms cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Warm cocoa-terracotta sidebar with cloud silhouettes at bottom-left, matching WuwaTappo */
.side {
  position: relative;
  width: 164px;
  flex: none;
  display: flex;
  flex-direction: column;
  padding: 14px 0 12px;
  box-sizing: border-box;
  background: linear-gradient(180deg, #A15E40 0%, #945235 100%);
  border-right: 2px solid #824429;
  overflow: hidden;
  user-select: none;
  transition: width 180ms ease;
}
.side::before,
.side::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 214, 184, 0.1);
  pointer-events: none;
}
.side::before {
  width: 170px;
  height: 170px;
  left: -48px;
  bottom: -54px;
}
.side::after {
  width: 130px;
  height: 130px;
  right: -36px;
  bottom: -64px;
}
.side.mini {
  width: 72px;
}

/* Chunky playful 2-line logo like WuwaTappo */
.logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 76px;
  padding: 2px 12px 10px;
  cursor: grab;
  position: relative;
  z-index: 1;
}
.logo:active {
  cursor: grabbing;
}
.logo-line {
  display: inline-flex;
  align-items: center;
  font-weight: 900;
  font-size: 30px;
  line-height: 0.96;
  letter-spacing: 0.5px;
  color: #FFE5A8;
  -webkit-text-stroke: 5px #5B2E17;
  paint-order: stroke fill;
  text-shadow: 0 3px 0 #5B2E17;
}
.logo-line.top {
  transform: rotate(-4deg) translateX(-4px);
  color: #FFE8AE;
}
.logo-line.bot {
  transform: rotate(-2deg) translateX(4px);
  color: #FFC39B;
  position: relative;
}
.sparks {
  margin-left: 2px;
  filter: drop-shadow(0 2px 0 #5B2E17);
}
.logo-mini {
  font-size: 24px;
  font-weight: 900;
  color: #FFE5A8;
  -webkit-text-stroke: 4px #5B2E17;
  paint-order: stroke fill;
  text-shadow: 0 2px 0 #5B2E17;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding-right: 12px;
  position: relative;
  z-index: 1;
}
nav button {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 52px;
  padding: 0 16px 0 22px;
  border: 2px solid transparent;
  border-left: 0;
  border-radius: 0 999px 999px 0;
  background: transparent;
  color: #F6DEC9;
  font: 800 17px var(--font);
  cursor: pointer;
  transition: background 140ms, color 140ms, transform 120ms, box-shadow 140ms;
}
nav button:hover:not(.on) {
  background: rgba(255, 236, 218, 0.12);
  color: #FFF5EB;
}
/* Active puffy capsule pill with #FC966E coral-peach fill and 3D bottom lip */
nav button.on {
  background: linear-gradient(180deg, #FFD4B8 0%, var(--accent) 100%);
  color: #562915;
  border-color: #C45D35;
  box-shadow: 0 4px 0 #74381F, inset 0 2px 0 rgba(255, 255, 255, 0.55);
}
.pip {
  margin-left: auto;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: 999px;
  background: var(--accent);
  color: #562915;
  border: 1.5px solid #5B2E17;
  font-size: 11px;
  font-weight: 900;
  display: grid;
  place-items: center;
}
nav button.on .pip {
  background: #FFF6EC;
  color: #7A3B1E;
  border-color: #B85832;
}
.pip.soft {
  background: rgba(255, 240, 225, 0.25);
  color: #FFF5EB;
  border-color: transparent;
}

.fold {
  margin: auto 12px 0 12px;
  height: 40px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #EDD0B6;
  font: 800 15px var(--font);
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  position: relative;
  z-index: 1;
  transition: background 140ms, color 140ms;
}
.fold:hover {
  background: rgba(255, 236, 218, 0.12);
  color: #FFF5EB;
}

.side.mini .lbl {
  display: none;
}
.side.mini nav {
  padding-right: 8px;
}
.side.mini nav button {
  justify-content: center;
  padding: 0;
}
.side.mini .pip {
  position: absolute;
  right: 4px;
  top: 4px;
}
.side.mini .fold {
  justify-content: center;
  padding: 0;
}

/* Main right-hand cream stage with wavy awning trim & rotated diamond close button */
.main {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--paper);
}
.awning {
  position: relative;
  height: 20px;
  flex: none;
  cursor: grab;
  user-select: none;
  background:
    repeating-linear-gradient(
      -32deg,
      rgba(228, 198, 166, 0.32) 0 8px,
      rgba(248, 232, 212, 0.55) 8px 16px
    ),
    #F3E2CE;
}
.awning:active {
  cursor: grabbing;
}
.wave {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -6px;
  width: 100%;
  height: 12px;
  display: block;
  pointer-events: none;
}

.close-diamond {
  position: absolute;
  top: 8px;
  right: 11px;
  z-index: 10;
  width: 28px;
  height: 28px;
  padding: 3px;
  margin: 0;
  box-sizing: border-box;
  border-radius: 8px;
  transform: rotate(45deg);
  background: linear-gradient(135deg, #FFB08E 0%, var(--accent) 100%);
  border: 2px solid #6F391F;
  box-shadow: 0 2.5px 0 #6F391F;
  color: #562915;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 140ms, filter 140ms;
}
.close-diamond:hover {
  filter: brightness(1.06);
  transform: rotate(45deg) scale(1.06);
}
.close-diamond:active {
  transform: rotate(45deg) translate(1px, 1px);
  box-shadow: 0 1px 0 #6F391F;
}
.diamond-rim {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  border-radius: 4px;
  border: 1.5px solid rgba(255, 246, 236, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
}
.diamond-rim svg {
  transform: rotate(-45deg);
  display: block;
}

.body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding-top: 6px;
}
.form-page {
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  padding: 18px 28px 28px;
}

@keyframes open {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(8px);
  }
}
</style>
