<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { settings } from "../stores/settings";
import { boxes, shards, tickets } from "../stores/player";
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
  { id: "dex", label: "收藏集", icon: "book" }, { id: "emotes", label: "表情", icon: "spark" },
  { id: "room", label: "联机", icon: "users" }, { id: "settings", label: "设置", icon: "sliders" },
];
const size = computed(() => ({ w: Math.min(960, viewport.value.w - 24), h: Math.min(700, viewport.value.h - 24) }));
const pos = computed(() => clamp(settings.panelX < 0
  ? { x: (viewport.value.w - size.value.w) / 2, y: (viewport.value.h - size.value.h) / 2 }
  : { x: settings.panelX, y: settings.panelY }, size.value));
const live = ref<{ x: number; y: number } | null>(null);
let drag: { px: number; py: number; x: number; y: number; id: number } | null = null;
function down(e: PointerEvent) {
  if (e.button !== 0 || (e.target as HTMLElement).closest("button, input")) return;
  drag = { px: e.clientX, py: e.clientY, x: pos.value.x, y: pos.value.y, id: e.pointerId };
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  void setDragging(true);
}
function move(e: PointerEvent) {
  if (drag && e.pointerId === drag.id) live.value = clamp({ x: drag.x + e.clientX - drag.px, y: drag.y + e.clientY - drag.py }, size.value);
}
function up(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  drag = null;
  void setDragging(false);
  if (live.value) { settings.panelX = live.value.x; settings.panelY = live.value.y; }
  live.value = null;
}
function onKey(e: KeyboardEvent) { if (e.key === "Escape" && !document.querySelector(".backdrop")) ui.panelOpen = false; }
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => { window.removeEventListener("keydown", onKey); if (drag) void setDragging(false); });
</script>

<template>
  <section class="panel" data-hit role="dialog" aria-label="AsoulTappo 面板"
    :style="{ ...skinVars, width: `${size.w}px`, height: `${size.h}px`, left: `${(live ?? pos).x}px`, top: `${(live ?? pos).y}px` }">
    <header @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
      <div class="wordmark"><svg viewBox="0 0 40 40" width="32" height="32" aria-hidden="true"><path d="M7 25V17C7 7 33 7 33 17v8c0 9-26 9-26 0Z" fill="#FC966E"/><path d="m12 11 2-5m6 4V4m6 7 2-5" stroke="#FC966E" stroke-width="2.5" stroke-linecap="round"/><circle cx="15" cy="21" r="1.5" fill="#613e31"/><circle cx="25" cy="21" r="1.5" fill="#613e31"/><path d="M18 25q2 2 4 0" fill="none" stroke="#613e31" stroke-width="1.5"/></svg><span><small>A-SOUL</small>Tappo<span class="star">✦</span></span></div>
      <nav aria-label="主导航"><button v-for="n in NAV" :key="n.id" :class="{ on: ui.page === n.id }" :aria-current="ui.page === n.id ? 'page' : undefined" @click="ui.page = n.id">{{ n.label }}</button></nav>
      <div class="resources">
        <button title="抽卡次数" @click="ui.page = 'dex'"><Icon name="book" :size="15" /><b>{{ tickets }}</b><small>抽</small></button>
        <button title="表情宝箱" @click="ui.page = 'emotes'"><Icon name="box" :size="16" /><b>{{ boxes }}</b></button>
        <span title="碎片"><Icon name="shard" :size="14" /><b>{{ shards }}</b></span>
      </div>
      <button class="close" aria-label="关闭面板" @click="ui.panelOpen = false"><Icon name="close" :size="18" /></button>
    </header>
    <main class="body" :key="settings.serverUrl">
      <KeepAlive>
        <CollectionPage v-if="ui.page === 'dex'" />
        <EmotesPage v-else-if="ui.page === 'emotes'" />
        <OnlinePage v-else-if="ui.page === 'room'" class="form-page ui-scroll" />
        <SettingsPage v-else class="form-page ui-scroll" @reset-pet="emit('resetPet')" />
      </KeepAlive>
    </main>
  </section>
</template>

<style scoped>
.panel { position: absolute; z-index: 40; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; border-radius: 12px; background: #fff; border: 1px solid #f0d9cd; box-shadow: 0 20px 60px #6f44332b, 0 2px 8px #6f443314; font-family: var(--font); color: var(--ink); animation: open 180ms ease-out; }
header { display: flex; align-items: center; gap: 24px; min-height: 64px; flex: none; padding: 0 16px 0 22px; border-bottom: 1px solid var(--line); cursor: grab; user-select: none; }
.wordmark { display: flex; align-items: center; gap: 8px; font-size: 22px; font-weight: 800; letter-spacing: -1px; line-height: 1; }
.wordmark > span { position: relative; }
.wordmark small { display: block; font-size: 8px; letter-spacing: 3px; margin-bottom: 4px; color: var(--ink-2); }
.star { position: absolute; right: -11px; top: 6px; color: #fc966e; font-size: 13px; }
nav { display: flex; align-self: stretch; gap: 26px; margin-left: 12px; }
nav button { position: relative; border: 0; background: transparent; padding: 0; font: 600 14px var(--font); cursor: pointer; color: var(--ink-2); }
nav button.on { color: var(--ink); }
nav button.on::after { content: ""; position: absolute; height: 3px; left: 0; right: 0; bottom: 0; background: var(--accent); border-radius: 2px 2px 0 0; }
nav button:hover { color: #ac5836; }
.resources { display: flex; align-items: center; gap: 4px; margin-left: auto; font-size: 13px; }
.resources > * { display: inline-flex; align-items: center; gap: 5px; padding: 7px; border: 0; background: transparent; color: var(--ink); font: inherit; white-space: nowrap; }
.resources button { cursor: pointer; border-radius: 4px; }
.resources button:hover { background: var(--paper-2); }
.resources :deep(.icon) { color: #bd6947; }
.resources small { font-size: 10px; color: var(--ink-2); }
.close { width: 28px; height: 28px; display: grid; place-items: center; background: none; border: 0; color: var(--ink-2); cursor: pointer; border-radius: 4px; }
.close:hover { background: var(--paper-2); }
.body { flex: 1; min-height: 0; overflow: hidden; }
.form-page { height: 100%; box-sizing: border-box; overflow: auto; padding: 24px 30px; }
@media (max-width: 760px) { header { gap: 12px; padding: 0 12px; flex-wrap: wrap; } .wordmark { font-size: 18px; } nav { gap: 16px; margin-left: 0; min-height: 54px; } .resources { gap: 0; } .resources > * { padding: 3px; } }
@media (max-width: 560px) { .wordmark { display: none; } .resources > span { display: none; } }
@keyframes open { from { opacity: 0; transform: translateY(6px); } }
</style>
