<script setup lang="ts">
// A pet standing somewhere on the desktop overlay. Drag it anywhere; a press that does not move is a `tap`.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { setDragging } from "../composables/tauri";
import { clamp, type Pos, type Size } from "../stores/desk";
import { dragged, isTap } from "./drag";

const props = defineProps<{ pos: Pos; label?: string }>();
const emit = defineEmits<{ moved: [pos: Pos]; size: [size: Size]; dragging: []; tap: [] }>();

const root = ref<HTMLElement | null>(null);
const live = ref<Pos | null>(null);
let start: { px: number; py: number; x: number; y: number; id: number } | null = null;
let moved = false;
let ro: ResizeObserver | undefined;

const size = (): Size => {
  const r = root.value?.getBoundingClientRect();
  return { w: r?.width ?? 0, h: r?.height ?? 0 };
};

function down(e: PointerEvent) {
  if (e.button !== 0) return;
  if ((e.target as HTMLElement).closest("button, input, [data-no-drag]")) return;
  start = { px: e.clientX, py: e.clientY, x: props.pos.x, y: props.pos.y, id: e.pointerId };
  moved = false;
  root.value?.setPointerCapture(e.pointerId);
  void setDragging(true);
}
function move(e: PointerEvent) {
  if (!start || e.pointerId !== start.id) return;
  const dx = e.clientX - start.px;
  const dy = e.clientY - start.py;
  if (!moved && !dragged(dx, dy)) return;
  moved = true;
  live.value = clamp({ x: start.x + dx, y: start.y + dy }, size());
  emit("dragging");
}
function up(e: PointerEvent) {
  if (!start || e.pointerId !== start.id) return;
  start = null;
  void setDragging(false);
  if (moved && live.value) emit("moved", live.value);
  live.value = null;
  if (isTap(moved, e.type)) emit("tap");
}

onMounted(() => {
  ro = new ResizeObserver(() => emit("size", size()));
  if (root.value) ro.observe(root.value);
});
onBeforeUnmount(() => {
  ro?.disconnect();
  if (start) void setDragging(false);
});
</script>

<template>
  <div
    ref="root" class="actor" :class="{ grabbing: !!live }" data-hit :aria-label="label"
    :style="{ transform: `translate(${(live ?? pos).x}px, ${(live ?? pos).y}px)` }"
    @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up"
  >
    <slot />
  </div>
</template>

<style scoped>
.actor { position: absolute; left: 0; top: 0; display: flex; flex-direction: column; align-items: center; cursor: grab; touch-action: none; will-change: transform; }
.actor.grabbing { cursor: grabbing; z-index: 30; }
</style>
