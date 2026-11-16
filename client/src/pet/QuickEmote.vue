<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useLift } from "./lift";
import { getEmote } from "../manifest";
import { assetUrl } from "../asset";
import { roomStatus } from "../roomStatus";
import Icon from "../ui/Icon.vue";

/**
 * The plate leads with small keys for the other pages: the tomato timer (`pomodoro`: it runs), the todos (`todo`: one
 * is past its time), and in a room the own status (`status`, "" for none; null leaves its key out).
 * `ceiling`: where the screen ends below the strip the dock opens above this viewport y (over the pet's head).
 */
const props = defineProps<{ keys: string[]; status?: string | null; pomodoro?: boolean; todo?: boolean; ceiling?: number }>();
defineEmits<{ pick: [key: string]; status: []; pomodoro: []; todo: [] }>();

const root = ref<HTMLElement>();
const { up, style: lift } = useLift(root, () => props.ceiling);

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
    ref="root"
    class="dock"
    :class="{ compact: list.length === 5, up }"
    :style="lift"
    data-hit
    data-no-drag
    role="menu"
    aria-label="快捷表情"
    @wheel.prevent="onWheel"
  >
    <div class="lead">
      <button
        type="button" class="ui-btn" :class="{ running: pomodoro }" role="menuitem" title="番茄钟" aria-label="番茄钟"
        @click="$emit('pomodoro')"
      >
        <Icon name="tomato" :size="14" />
      </button>
      <button
        type="button" class="ui-btn" :class="{ running: todo }" role="menuitem" title="待办" aria-label="待办"
        @click="$emit('todo')"
      >
        <Icon name="todo" :size="14" />
      </button>
      <button
        v-if="status != null" type="button" class="ui-btn tall" role="menuitem" title="我的状态" aria-label="我的状态"
        @click="$emit('status')"
      >
        <Icon :name="roomStatus(status)?.icon ?? 'status'" :size="14" />
      </button>
    </div>
    <i class="sep" aria-hidden="true"></i>
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
.dock.up {
  top: auto;
  bottom: calc(100% + 10px);
  animation-name: rise-in;
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

/* Keys to the other pages: two stacked as tall as an emote key, and in a room the status key beside them at full height. */
.lead {
  flex: none;
  display: grid;
  grid-auto-flow: column;
  grid-template-rows: repeat(2, 20px);
  gap: 4px;
}
.lead .ui-btn {
  --key-lip-h: 2px;
  width: 30px;
  height: 20px;
  padding: 0;
  border-radius: 7px;
  color: var(--ink-2);
}
.lead .ui-btn.tall {
  grid-row: 1 / span 2;
  height: auto;
  border-radius: 8px;
}
.lead .ui-btn.running {
  color: var(--c-600);
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
@keyframes rise-in {
  from {
    opacity: 0;
    transform: translate(-50%, 8px);
  }
}
</style>
