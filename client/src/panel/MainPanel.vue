<script setup lang="ts">
// The main panel: a floating window on the desk overlay with a sidebar and five pages.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { settings } from "../stores/settings";
import { counter } from "../stores/counter";
import { boxes, shards } from "../stores/player";
import { inRoom, members } from "../stores/room";
import { skinVars } from "../stores/theme";
import { clamp, viewport } from "../stores/desk";
import { ui, type Page } from "../stores/ui";
import { setDragging } from "../composables/tauri";
import Icon from "../ui/Icon.vue";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import BackpackPage from "./BackpackPage.vue";
import CollectionPage from "./CollectionPage.vue";
import CraftPage from "./CraftPage.vue";
import OnlinePage from "./OnlinePage.vue";
import SettingsPage from "./SettingsPage.vue";

const emit = defineEmits<{ resetPet: [] }>();
const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "bag", label: "背包", icon: "bag" },
  { id: "dex", label: "图鉴", icon: "book" },
  { id: "craft", label: "合成", icon: "craft" },
  { id: "room", label: "联机", icon: "users" },
  { id: "settings", label: "设置", icon: "sliders" },
];
const title = computed(() => NAV.find((n) => n.id === ui.page)?.label ?? "");

const size = computed(() => ({ w: Math.min(900, viewport.value.w - 24), h: Math.min(620, viewport.value.h - 24) }));
const pos = computed(() =>
  settings.panelX < 0
    ? clamp({ x: (viewport.value.w - size.value.w) / 2, y: (viewport.value.h - size.value.h) / 2 }, size.value)
    : clamp({ x: settings.panelX, y: settings.panelY }, size.value),
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
  if (!drag || e.pointerId !== drag.id) return;
  live.value = clamp({ x: drag.x + e.clientX - drag.px, y: drag.y + e.clientY - drag.py }, size.value);
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
</script>

<template>
  <section
    class="panel" data-hit role="dialog" aria-label="AsoulTappo 面板"
    :style="{ ...skinVars, width: `${size.w}px`, height: `${size.h}px`, left: `${(live ?? pos).x}px`, top: `${(live ?? pos).y}px` }"
  >
    <aside class="side" :class="{ mini: settings.sidebarCollapsed }">
      <div class="logo" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
        <span class="mark">T</span><span class="word"><small>A-SOUL</small>Tappo</span>
      </div>
      <nav>
        <button
          v-for="n in NAV" :key="n.id" type="button" :class="{ on: ui.page === n.id }" :title="n.label"
          :aria-current="ui.page === n.id ? 'page' : undefined" @click="ui.page = n.id"
        >
          <Icon :name="n.icon" :size="20" />
          <span class="lbl">{{ n.label }}</span>
          <span v-if="n.id === 'craft' && boxes" class="pip">{{ boxes }}</span>
          <span v-else-if="n.id === 'room' && inRoom" class="pip soft">{{ members.size }}</span>
        </button>
      </nav>
      <div class="me">
        <CharacterAvatar :character="settings.character" :size="34" />
        <span class="who"><b>{{ settings.nick || "匿名小面包" }}</b><small>今日 {{ counter.today.toLocaleString("en-US") }}</small></span>
      </div>
      <button type="button" class="fold" :title="settings.sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="settings.sidebarCollapsed = !settings.sidebarCollapsed">
        <Icon :name="settings.sidebarCollapsed ? 'unfold' : 'fold'" :size="18" /><span class="lbl">收起侧栏</span>
      </button>
    </aside>

    <div class="main">
      <header @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
        <h2>{{ title }}</h2>
        <button type="button" class="chip" title="宝箱" @click="ui.page = 'craft'">
          <svg width="15" height="15" viewBox="0 0 64 64" aria-hidden="true"><rect x="9" y="28" width="46" height="26" rx="4" fill="#e9a640" /><path d="M9 30a23 16 0 0 1 46 0z" fill="#f2c066" /></svg>
          {{ boxes }}
        </button>
        <span class="chip" title="碎片"><Icon name="shard" :size="15" />{{ shards }}</span>
        <button type="button" class="close" aria-label="关闭面板" title="关闭（Esc）" @click="ui.panelOpen = false"><Icon name="close" :size="18" /></button>
      </header>
      <div class="body ui-scroll">
        <KeepAlive>
          <BackpackPage v-if="ui.page === 'bag'" />
          <CollectionPage v-else-if="ui.page === 'dex'" />
          <CraftPage v-else-if="ui.page === 'craft'" />
          <OnlinePage v-else-if="ui.page === 'room'" />
          <SettingsPage v-else @reset-pet="emit('resetPet')" />
        </KeepAlive>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  position: absolute; left: 0; top: 0; z-index: 40; display: flex; overflow: hidden; box-sizing: border-box;
  border-radius: var(--r-xl); background: var(--paper); border: 1px solid var(--line-2); box-shadow: var(--shadow-2);
  font-family: var(--font); color: var(--ink); animation: open 180ms ease-out;
}
.side {
  width: 168px; flex: none; display: flex; flex-direction: column; gap: 2px; padding: 14px 10px 10px; box-sizing: border-box;
  background: var(--paper-2); border-right: 1px solid var(--line); transition: width 160ms;
}
.side.mini { width: 56px; }
.logo { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 4px; margin-bottom: 14px; cursor: grab; user-select: none; overflow: hidden; }
.mark { width: 28px; height: 28px; flex: none; border-radius: var(--r-m); display: grid; place-items: center; background: var(--accent); color: var(--on-accent); font-size: 16px; font-weight: 800; }
.word { display: flex; flex-direction: column; line-height: 1.05; font-size: 17px; font-weight: 800; letter-spacing: -0.01em; white-space: nowrap; }
.word small { font-size: 9px; font-weight: 700; letter-spacing: 0.14em; color: var(--ink-3); }
nav { display: flex; flex-direction: column; gap: 2px; flex: 1; }
nav button, .fold {
  position: relative; display: flex; align-items: center; gap: 10px; height: 36px; padding: 0 10px; border: none; border-radius: var(--r-m);
  background: none; color: var(--ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap; transition: background 120ms, color 120ms;
}
nav button:hover, .fold:hover { background: rgba(43, 35, 38, 0.05); color: var(--ink); }
nav button.on { background: rgba(var(--accent-rgb), 0.14); color: var(--ink); }
nav button.on :deep(.icon) { color: var(--accent); }
.pip { margin-left: auto; min-width: 18px; height: 18px; padding: 0 5px; box-sizing: border-box; border-radius: var(--r-s); display: grid; place-items: center; font-size: 11px; font-weight: 700; background: var(--accent); color: var(--on-accent); }
.pip.soft { background: var(--paper-3); color: var(--ink-2); }
.side.mini .lbl, .side.mini .who, .side.mini .word { display: none; }
.side.mini nav button, .side.mini .fold { justify-content: center; padding: 0; }
.side.mini .pip { position: absolute; right: 2px; top: 2px; min-width: 14px; height: 14px; padding: 0 3px; font-size: 9px; }
.me { display: flex; align-items: center; gap: 8px; padding: 8px 6px; margin-bottom: 2px; border-top: 1px solid var(--line); }
.side.mini .me { justify-content: center; padding: 8px 0; }
.who { display: flex; flex-direction: column; min-width: 0; }
.who b { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who small { font-size: 11px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.fold { height: 32px; font-size: 12px; color: var(--ink-3); }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
header { display: flex; align-items: center; gap: 4px; height: 52px; padding: 0 12px 0 20px; flex: none; border-bottom: 1px solid var(--line); cursor: grab; user-select: none; }
header h2 { margin: 0 auto 0 0; font-size: 16px; font-weight: 700; }
.chip { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 8px; border-radius: var(--r-m); border: none; background: none; font: inherit; font-size: 13px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
button.chip { cursor: pointer; }
button.chip:hover { background: var(--paper-2); }
.chip :deep(.icon) { color: var(--accent); }
.close { width: 28px; height: 28px; border-radius: var(--r-m); border: none; display: grid; place-items: center; background: none; color: var(--ink-2); cursor: pointer; margin-left: 6px; }
.close:hover { color: var(--ink); background: var(--paper-2); }
.body { flex: 1; overflow: auto; padding: 18px 20px 24px; }
@keyframes open { from { opacity: 0; transform: translateY(6px); } }
</style>
