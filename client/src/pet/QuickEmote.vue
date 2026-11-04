<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getEmote } from "../manifest";
import { assetUrl } from "../asset";

const props = defineProps<{ keys: string[] }>();
defineEmits<{ pick: [key: string] }>();

const list = computed(() => props.keys.map((k) => ({ key: k, e: getEmote(k) })).filter((x) => x.e));

// Up to 5 emotes fit in one row directly under CounterBar without arrows;
// 6+ emotes show 4 full unclipped tiles at a time with < > arrows and wheel support.
const PAGE_SIZE = 4;
const needsPager = computed(() => list.value.length > 5);
const start = ref(0);

watch(
  () => list.value.length,
  (len) => {
    if (start.value > Math.max(0, len - PAGE_SIZE)) {
      start.value = Math.max(0, len - PAGE_SIZE);
    }
  },
);

const visible = computed(() =>
  needsPager.value ? list.value.slice(start.value, start.value + PAGE_SIZE) : list.value,
);

const canPrev = computed(() => start.value > 0);
const canNext = computed(() => start.value + PAGE_SIZE < list.value.length);

function prev() {
  start.value = Math.max(0, start.value - PAGE_SIZE);
}
function next() {
  start.value = Math.min(Math.max(0, list.value.length - PAGE_SIZE), start.value + PAGE_SIZE);
}
function onWheel(e: WheelEvent) {
  if (!needsPager.value) return;
  const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
  if (delta > 0 && canNext.value) start.value = Math.min(list.value.length - PAGE_SIZE, start.value + 1);
  else if (delta < 0 && canPrev.value) start.value = Math.max(0, start.value - 1);
}
</script>

<template>
  <div
    class="dock"
    :class="{ compact: list.length === 5 }"
    data-hit
    data-no-drag
    role="menu"
    aria-label="快捷表情"
    @wheel.prevent="onWheel"
  >
    <button
      v-if="needsPager"
      type="button"
      class="nav-arrow"
      :disabled="!canPrev"
      aria-label="上一组表情"
      @click.stop="prev"
    >
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <path d="M10 3.5L5.5 8 10 12.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <div class="row">
      <button
        v-for="x in visible" :key="x.key" type="button"
        class="emo" role="menuitem" :title="x.e!.name"
        @click="$emit('pick', x.key)"
      >
        <img :src="assetUrl(x.e!.img)" :alt="x.e!.name" draggable="false" />
      </button>
    </div>

    <button
      v-if="needsPager"
      type="button"
      class="nav-arrow"
      :disabled="!canNext"
      aria-label="下一组表情"
      @click.stop="next"
    >
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <path d="M6 3.5L10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
/* Single-row dock under the counter bar; tiles are never clipped in half */
.dock {
  position: absolute;
  left: 50%;
  top: calc(100% + 10px);
  transform: translateX(-50%);
  z-index: 20;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  box-sizing: border-box;
  background: var(--surface);
  box-shadow: 4px 4px 0 var(--accent), 0 8px 20px rgba(43, 37, 48, 0.2);
  font-family: var(--font);
  animation: drop-in 260ms var(--ease-out);
  cursor: default;
}
.row {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: nowrap;
  gap: 6px;
}
.dock.compact .row {
  gap: 5px;
}
.emo {
  width: 46px;
  height: 46px;
  flex: 0 0 46px;
  padding: 5px;
  margin: 0;
  box-sizing: border-box;
  border: 0;
  background: var(--accent-tint);
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 200ms var(--ease-out), background 140ms;
}
.dock.compact .emo {
  width: 41px;
  height: 41px;
  flex: 0 0 41px;
  padding: 4px;
}
.emo:hover {
  background: var(--accent-soft);
  transform: translate(-1px, -2px);
}
.emo:active {
  transform: translate(1px, 1px);
}
.emo img {
  max-width: 34px;
  max-height: 34px;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
  margin: auto;
  filter: var(--sticker);
}
.dock.compact .emo img {
  max-width: 30px;
  max-height: 30px;
}

.nav-arrow {
  width: 20px;
  height: 36px;
  flex: 0 0 20px;
  padding: 0;
  margin: 0;
  box-sizing: border-box;
  border: 0;
  background: var(--accent-tint);
  color: var(--ink);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transform: skewX(var(--skew));
  transition: background 140ms;
}
.nav-arrow:hover:not(:disabled) {
  background: var(--accent);
}
.nav-arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

@keyframes drop-in {
  from {
    opacity: 0;
    transform: translate(calc(-50% - 10px), -8px);
  }
}
</style>
