<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getEmote } from "../manifest";
import { assetUrl } from "../asset";
import { roomStatus } from "../roomStatus";
import Icon from "../ui/Icon.vue";

/** `status` is the own room status ("" for none) and adds a key that opens the statuses; null leaves it out. */
const props = defineProps<{ keys: string[]; status?: string | null }>();
defineEmits<{ pick: [key: string]; status: [] }>();

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
    <template v-if="status != null">
      <button type="button" class="emo ui-btn" role="menuitem" title="我的状态" aria-label="我的状态" @click="$emit('status')">
        <Icon :name="roomStatus(status)?.icon ?? 'status'" :size="20" />
      </button>
      <i class="sep" aria-hidden="true"></i>
    </template>
    <button
      v-if="needsPager"
      type="button"
      class="nav-arrow ui-btn ghost"
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
        class="emo ui-btn" role="menuitem" :title="x.e!.name"
        @click="$emit('pick', x.key)"
      >
        <img :src="assetUrl(x.e!.thumb ?? x.e!.img)" :alt="x.e!.name" draggable="false" />
      </button>
    </div>

    <button
      v-if="needsPager"
      type="button"
      class="nav-arrow ui-btn ghost"
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
/* A paper plate of keys under the counter strip, one row; keys are never clipped in half. */
.dock {
  position: absolute;
  left: 50%;
  top: calc(100% + 10px);
  transform: translateX(-50%);
  z-index: 20;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 8px 11px;
  box-sizing: border-box;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 8px 20px -6px rgba(var(--shadow-rgb), 0.35);
  font-family: var(--font);
  animation: drop-in var(--dur-base) var(--ease-out);
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
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  padding: 4px;
}
.dock.compact .emo {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
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

.sep {
  flex: none;
  width: 1px;
  height: 28px;
  margin: 0 2px;
  background: var(--c-100);
}

.nav-arrow {
  width: 22px;
  height: 40px;
  flex: 0 0 22px;
  padding: 0;
  color: var(--ink);
}
.nav-arrow:disabled {
  opacity: 0.35;
}

@keyframes drop-in {
  from {
    opacity: 0;
    transform: translate(calc(-50% - 10px), -8px);
  }
}
</style>
