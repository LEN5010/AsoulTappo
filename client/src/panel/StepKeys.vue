<script setup lang="ts">
// Previous and next keys on the left and right edges of the positioned parent. A key with nowhere to go is
// hidden but keeps its place. With `keyboard`, the Left and Right arrow keys step as well.
import { onBeforeUnmount, onMounted } from "vue";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ prev: boolean; next: boolean; keyboard?: boolean }>();
const emit = defineEmits<{ step: [delta: -1 | 1] }>();

function onKey(e: KeyboardEvent) {
  if (!props.keyboard || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || e.isComposing) return;
  if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]")) return;
  const delta = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
  if (!delta || !(delta < 0 ? props.prev : props.next)) return;
  e.preventDefault();
  emit("step", delta);
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <button type="button" class="step prev ui-btn small ghost" :class="{ off: !prev }" :disabled="!prev" aria-label="上一张" @click.stop="emit('step', -1)">
    <Icon name="back" :size="16" />
  </button>
  <button type="button" class="step next ui-btn small ghost" :class="{ off: !next }" :disabled="!next" aria-label="下一张" @click.stop="emit('step', 1)">
    <Icon name="back" :size="16" />
  </button>
</template>

<style scoped>
/* The same frosted flat key as the video controls, so it reads over any artwork. */
.step.ui-btn {
  --key-top: rgba(255, 255, 255, 0.86);
  --key-bottom: rgba(255, 255, 255, 0.86);
  --key-y: 0px;
  --key-lip-h: 0px;
  position: absolute;
  top: 50%;
  z-index: 4;
  width: 32px;
  padding: 0;
  margin-top: -14px;
  color: var(--ink);
  backdrop-filter: blur(6px);
}
.step.ui-btn:hover:not(:disabled) {
  --key-top: #fff;
  --key-bottom: #fff;
}
.step.ui-btn:active:not(:disabled) {
  --key-top: var(--c-100);
  --key-bottom: var(--c-100);
}
.prev { left: var(--step-inset, 10px); }
.next { right: var(--step-inset, 10px); }
.next svg { transform: rotate(180deg); }
.off { visibility: hidden; }
</style>
