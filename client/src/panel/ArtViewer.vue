<script setup lang="ts">
// Full-panel viewer for one artwork: the wheel or a double click zooms towards the pointer, a drag pans the
// zoomed art, the arrow keys step and Escape leaves. It sits in a Modal's `front` slot, over the sheet.
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { reducedMotion } from "../stores/theme";
import { takeFocus, trapTab } from "../ui/focus";
import Icon from "../ui/Icon.vue";
import type { Tilt } from "../holo/shader";
import { clampPan, FIT, fitSize, zoomAt, type Size, type View } from "./album";
import StepKeys from "./StepKeys.vue";

const props = defineProps<{
  /** Changes with the artwork shown; the zoom resets. */
  id: string;
  /** Width / height of the art until its image or video reports its own. */
  ratio: number;
  label?: string;
  /** Whether stepping is offered at all, and where it can go. */
  steps?: boolean;
  prev?: boolean;
  next?: boolean;
  /** A lean for the art (a holo card under the pointer); it stays level while zoomed. */
  tilt?: Tilt;
}>();
const emit = defineEmits<{ close: []; step: [delta: -1 | 1] }>();

/** Room kept clear at scale 1 for the side keys and the close key. */
const GUTTER_X = 60;
const GUTTER_Y = 56;
const DOUBLE_SCALE = 2.2;

const root = ref<HTMLElement>();
const stage = ref<HTMLElement>();
const box = reactive<Size>({ w: 0, h: 0 });
const measured = ref(0);
const ratio = computed(() => measured.value || props.ratio);
const size = computed(() => fitSize(ratio.value, { w: box.w - GUTTER_X * 2, h: box.h - GUTTER_Y * 2 }));
const view = ref<View>(FIT);
const eased = ref(false);
const dragging = ref(false);
const zoomed = computed(() => view.value.scale > 1.001);
/** Pan and zoom from the top left corner; a lean turns the art about its centre on top of that. */
const transform = computed(() => {
  const { x, y, scale } = view.value;
  const move = `translate(${x}px, ${y}px) scale(${scale})`;
  const t = props.tilt;
  if (!t || zoomed.value || (!t.rx && !t.ry)) return move;
  const cx = size.value.w / 2;
  const cy = size.value.h / 2;
  return `${move} translate(${cx}px, ${cy}px) perspective(1600px) rotateX(${t.rx.toFixed(2)}deg) rotateY(${t.ry.toFixed(2)}deg) translate(${-cx}px, ${-cy}px)`;
});

watch(() => props.id, () => {
  view.value = FIT;
  eased.value = false;
});
// A resize keeps the zoom but closes any gap it opened.
watch([size, () => box.w, () => box.h], () => (view.value = clampPan(view.value, size.value, box)));

/** The pointer relative to the art's top left at scale 1; the art is centred in the stage. */
function pointAt(e: MouseEvent) {
  const r = stage.value!.getBoundingClientRect();
  return { x: e.clientX - r.left - (box.w - size.value.w) / 2, y: e.clientY - r.top - (box.h - size.value.h) / 2 };
}

function onWheel(e: WheelEvent) {
  const lines = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? box.h : 1;
  // A trackpad pinch arrives as a wheel with ctrlKey and small deltas.
  const factor = Math.exp(-e.deltaY * lines * (e.ctrlKey ? 0.01 : 0.002));
  eased.value = false;
  view.value = zoomAt(view.value, view.value.scale * factor, pointAt(e), size.value, box);
}

function onDouble(e: MouseEvent) {
  eased.value = !reducedMotion.value;
  view.value = zoomed.value ? FIT : zoomAt(view.value, DOUBLE_SCALE, pointAt(e), size.value, box);
}

// Only a press that starts on the dim area leaves; one that starts on the art and slips off does not.
let pressedStage = false;
let drag: { id: number; x: number; y: number; from: View } | null = null;
function onDown(e: PointerEvent) {
  pressedStage = false;
  if (e.button !== 0 || !zoomed.value) return;
  drag = { id: e.pointerId, x: e.clientX, y: e.clientY, from: view.value };
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  eased.value = false;
  dragging.value = true;
}
function onMove(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  const { from } = drag;
  view.value = clampPan({ scale: from.scale, x: from.x + e.clientX - drag.x, y: from.y + e.clientY - drag.y }, size.value, box);
}
function onUp(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  drag = null;
  dragging.value = false;
}

/** The image or video inside reports its real shape once it loads. */
function onLoad(e: Event) {
  const el = e.target;
  if (el instanceof HTMLImageElement && el.naturalHeight) measured.value = el.naturalWidth / el.naturalHeight;
  else if (el instanceof HTMLVideoElement && el.videoHeight) measured.value = el.videoWidth / el.videoHeight;
}

// Capture phase on window runs before the Modal's own listener, so Escape leaves the viewer first and Tab
// stays inside it.
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
  else if (e.key === "Tab" && root.value) trapTab(root.value, e);
  else if ((e.key === "ArrowLeft" && props.prev) || (e.key === "ArrowRight" && props.next)) {
    if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    emit("step", e.key === "ArrowLeft" ? -1 : 1);
  } else return;
  e.stopImmediatePropagation();
}

let observer: ResizeObserver | undefined;
let release: (() => void) | undefined;
onMounted(async () => {
  window.addEventListener("keydown", onKey, true);
  // The Modal teleports with `defer`, so the stage exists only after the next tick.
  await nextTick();
  if (!stage.value) return;
  observer = new ResizeObserver(([entry]) => {
    box.w = entry!.contentRect.width;
    box.h = entry!.contentRect.height;
  });
  observer.observe(stage.value);
  release = takeFocus(root.value);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey, true);
  observer?.disconnect();
  release?.();
});
</script>

<template>
  <div ref="root" class="viewer" :class="{ calm: reducedMotion }" role="dialog" aria-modal="true" :aria-label="label" tabindex="-1">
    <div ref="stage" class="stage" @pointerdown.self="pressedStage = true" @click.self="pressedStage && emit('close')" @wheel.prevent="onWheel">
      <div
        class="frame" :class="{ zoomed, dragging, eased }"
        :style="{ width: `${size.w}px`, height: `${size.h}px`, transform }"
        @dblclick="onDouble" @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp"
        @dragstart.prevent @load.capture="onLoad" @loadedmetadata.capture="onLoad"
      >
        <slot />
      </div>
    </div>
    <StepKeys v-if="steps" :prev="!!prev" :next="!!next" @step="emit('step', $event)" />
    <div v-if="$slots.controls" class="controls"><slot name="controls" /></div>
    <button type="button" class="x ui-btn small ghost" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="16" /></button>
  </div>
</template>

<style scoped>
.viewer {
  --step-inset: 14px;
  position: absolute;
  inset: 0;
  z-index: 1;
  outline: none;
  background: rgba(var(--shadow-rgb), 0.6);
  animation: fade var(--dur-base) var(--ease-out);
}
.stage {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.frame {
  flex: none;
  transform-origin: 0 0;
  overflow: hidden;
  border-radius: var(--radius-m);
  cursor: zoom-in;
  touch-action: none;
  user-select: none;
}
.frame.zoomed { cursor: grab; }
.frame.dragging { cursor: grabbing; }
.frame.eased { transition: transform var(--dur-slow) var(--ease-out); }
.frame > :slotted(img),
.frame > :slotted(video) {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
  -webkit-user-drag: none;
}
.calm,
.calm .frame.eased {
  animation: none;
  transition: none;
}
/* Frosted flat keys, as over the card artwork. */
.x.ui-btn,
.controls :slotted(.ui-btn),
.controls :slotted(.ui-btn[aria-pressed]:not(:disabled)) {
  --key-top: rgba(255, 255, 255, 0.86);
  --key-bottom: rgba(255, 255, 255, 0.86);
  --key-y: 0px;
  --key-lip-h: 0px;
  width: 32px;
  padding: 0;
  color: var(--ink);
  backdrop-filter: blur(6px);
}
.x.ui-btn:hover:not(:disabled),
.controls :slotted(.ui-btn:hover:not(:disabled)) {
  --key-top: #fff;
  --key-bottom: #fff;
}
.x.ui-btn {
  position: absolute;
  top: 12px;
  right: 14px;
  z-index: 4;
}
.controls {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 4;
  display: flex;
  gap: 8px;
}
@keyframes fade { from { opacity: 0; } }
</style>
