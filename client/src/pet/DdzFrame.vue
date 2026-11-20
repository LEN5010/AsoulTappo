<script setup lang="ts">
// The browser preview's dou dizhu window: the table (panel/ddz/DdzTable.vue) in a frame of the window's size over the
// desk page, which its wall moves. The app opens a window of its own instead (stores/ui.ts, openDdzWindow).
import { onBeforeUnmount, reactive } from "vue";
import DdzTable from "../panel/ddz/DdzTable.vue";
import { noteDdzWindowClosed } from "../stores/ddz";
import { ddzFrame } from "../stores/ui";

/** The window's size in the app (src-tauri/src/lib.rs, DDZ_SIZE). */
const W = 1180;
const H = 740;
/** How far the frame was moved from the middle of the page. */
const at = reactive({ x: 0, y: 0 });
let from: { x: number; y: number; px: number; py: number } | null = null;

function onMove(e: PointerEvent) {
  if (!from) return;
  at.x = from.x + e.clientX - from.px;
  at.y = from.y + e.clientY - from.py;
}
function onUp() {
  from = null;
  window.removeEventListener("pointermove", onMove);
  window.removeEventListener("pointerup", onUp);
}
function drag(e: PointerEvent) {
  from = { x: at.x, y: at.y, px: e.clientX, py: e.clientY };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}
function close() {
  ddzFrame.open = false;
  noteDdzWindowClosed();
}
onBeforeUnmount(onUp);
</script>

<template>
  <div
    class="ddz-frame" data-hit data-no-drag
    :style="{ '--w': `${W}px`, '--h': `${H}px`, translate: `calc(-50% + ${at.x}px) calc(-50% + ${at.y}px)` }"
  >
    <DdzTable @close="close" @drag="drag" />
  </div>
</template>

<style scoped>
.ddz-frame {
  position: fixed;
  left: 50%;
  top: 50%;
  z-index: 3000;
  width: min(var(--w), 100vw - 24px);
  height: min(var(--h), 100vh - 24px);
  border-radius: var(--radius-l);
  box-shadow:
    0 0 0 1px rgba(var(--c-900-rgb), 0.14),
    0 24px 60px -24px rgba(var(--c-900-rgb), 0.55);
  pointer-events: auto;
}
</style>
