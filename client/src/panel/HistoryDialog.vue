<script setup lang="ts">
// The save's own drops (behind the clock key in the resonance page's bottom bar): one row a drop, newest first under
// the day it came on, more pages as the list is scrolled to its end.
import { computed, nextTick, onMounted, ref } from "vue";
import { byDay, clockOf, rowsOf, type HistoryRow } from "../history";
import { loadHistory } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import ItemArt from "../ui/ItemArt.vue";
import Modal from "../ui/Modal.vue";

defineEmits<{ close: [] }>();

const rows = ref<HistoryRow[]>([]);
/** The page to ask next; null at the end of the history. */
let next: number | null | undefined;
const loading = ref(false);
const ended = ref(false);
const error = ref("");
const list = ref<HTMLElement>();
const now = Date.now();
const days = computed(() => byDay(rows.value, now));

/** How near its end (px) the list asks for the next page. */
const NEAR = 240;
async function more() {
  if (loading.value || ended.value) return;
  loading.value = true;
  error.value = "";
  const r = await loadHistory(next ?? undefined);
  loading.value = false;
  if (!r.ok) {
    error.value = r.message;
    return;
  }
  rows.value.push(...rowsOf(r.page.drops));
  next = r.page.next;
  ended.value = next === null;
  // A page of drops this client cannot show leaves the list short of its end: go on.
  await nextTick();
  fill();
}
function fill() {
  const el = list.value;
  if (el && !error.value && el.scrollTop + el.clientHeight > el.scrollHeight - NEAR) void more();
}
onMounted(more);
</script>

<template>
  <Modal title="共鸣记录" heading @close="$emit('close')">
    <div ref="list" class="list ui-scroll" @scroll.passive="fill">
      <section v-for="d in days" :key="d.key">
        <h4 class="day">{{ d.label }}</h4>
        <ol>
          <li v-for="r in d.rows" :key="r.id" class="row" :class="r.rarity">
            <span class="art"><ItemArt :item="r.item" :size="36" /></span>
            <span class="meta">
              <b class="name">{{ r.item.name }}</b>
              <span class="tags">
                <span v-if="r.tier" class="tier"><i class="swatch" aria-hidden="true"></i>{{ r.tier }}</span>
                <i v-if="r.holo" class="ui-tag holo">镭射</i>
                <i v-if="r.from" class="ui-tag from">{{ r.from }}</i>
              </span>
            </span>
            <i v-if="r.fresh" class="ui-tag">新</i>
            <time>{{ clockOf(r.ts) }}</time>
          </li>
        </ol>
      </section>
      <p v-if="error" class="foot" role="alert">
        <span class="ui-error">{{ error }}</span>
        <button type="button" class="ui-btn small" @click="more">重试</button>
      </p>
      <p v-else-if="ended && !rows.length" class="foot empty">还没有记录</p>
      <p v-else-if="loading" class="foot" role="status" aria-label="加载中"><i class="dots" :class="{ calm: reducedMotion }" aria-hidden="true"></i></p>
    </div>
  </Modal>
</template>

<style scoped>
/* A fixed window on the list, so the sheet keeps its size while pages come in. */
.list {
  height: min(520px, calc(100vh - 176px));
  margin: 0 -12px;
  padding: 0 12px;
  overflow-y: auto;
}
.day {
  position: sticky;
  top: 0;
  z-index: 1;
  margin: 0;
  padding: 10px 0 6px;
  background: var(--surface);
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink-3);
}
ol {
  margin: 0;
  padding: 0;
  list-style: none;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  box-shadow: inset 0 -1px 0 var(--c-100);
}
.row:last-child {
  box-shadow: none;
}
.art {
  flex: none;
  border-radius: var(--radius-s);
  overflow: hidden;
  background: var(--c-50);
}
.meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 var(--fs-body)/1.2 var(--font);
  color: var(--ink);
}
.tags {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.tier {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
/* The tiers' marks, as the odds table draws them. */
.swatch {
  flex: none;
  width: 4px;
  height: 11px;
  border-radius: 2px;
  background: var(--swatch, var(--c-200));
}
.legendary { --swatch: var(--grad-gold); }
.skin { --swatch: var(--c-500); }
.epic { --swatch: var(--c-800); }
.limited { --swatch: var(--pearl); }
.rare { --swatch: var(--c-400); }
.uncommon { --swatch: var(--c-300); }
.legendary .name {
  color: var(--c-800);
}
.ui-tag.holo {
  background: var(--grad-holo);
}
.ui-tag.from {
  --tag-bg: var(--c-100);
  --tag-fg: var(--c-800);
  overflow: hidden;
  text-overflow: ellipsis;
}
time {
  flex: none;
  min-width: 34px;
  text-align: right;
  font: 700 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-3);
}
.foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin: 0;
  padding: 16px 0 8px;
  font-size: var(--fs-body);
  color: var(--ink-3);
}
.foot.empty {
  height: 100%;
  box-sizing: border-box;
  padding: 0;
}
.foot .ui-error {
  margin: 0;
}
/* Three dots taking turns while a page is on its way. */
.dots {
  width: 33px;
  height: 6px;
  background: radial-gradient(circle 3px, var(--c-400) 96%, transparent) 0 0 / 11px 6px repeat-x;
  animation: wait 900ms steps(3, jump-none) infinite;
}
.dots.calm {
  animation: none;
}
@keyframes wait {
  from { clip-path: inset(0 22px 0 0); }
  to { clip-path: inset(0 0 0 0); }
}
</style>
