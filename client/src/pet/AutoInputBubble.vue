<script setup lang="ts">
// Over the pet once the server counts this save's input as automatic (an auto-clicker, a macro). Stays until its key
// opens the note behind it (AutoInputNote.vue). The other bubbles over the pet are white paper; this one is a coral
// plate with a breathing glow, so it is not taken for one of them.
import { ref } from "vue";
import { useCentredShift, type PetMiddle } from "./centredShift";

const props = defineProps<{ middle?: PetMiddle }>();
const emit = defineEmits<{ open: [] }>();
const paper = ref<HTMLElement>();
const shift = useCentredShift(paper, () => props.middle);
</script>

<template>
  <div class="anchor">
    <Transition name="alert" appear>
      <div ref="paper" class="auto" data-hit="keep" data-no-drag role="alert" :style="{ '--shift': `${shift}px` }">
        <span class="mark" aria-hidden="true">!</span>
        <p>识别到自动点击</p>
        <button type="button" class="ui-btn small" @click="emit('open')">看看</button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 6; }
.auto {
  position: absolute; left: 0; bottom: 10px; display: flex; align-items: center; gap: 10px; width: max-content;
  padding: 10px 10px 10px 12px; transform: translateX(calc(-50% + var(--shift, 0px))); border-radius: var(--radius-l);
  background: var(--grad-sky); color: var(--ink);
  box-shadow: 0 8px 18px -6px rgba(var(--c-900-rgb), 0.45), var(--glow-l);
  animation: breathe 2.2s var(--ease-in-out) infinite alternate;
}
/* The point stays on the pet when the plate shifts. */
.auto::after {
  content: ""; position: absolute; left: calc(50% - var(--shift, 0px)); top: 100%; translate: -50% -1px;
  border: 8px solid transparent; border-top-color: var(--c-500); border-bottom: 0;
}
.mark {
  flex: none; display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
  background: var(--surface); color: var(--c-700); font: 800 var(--fs-section)/1 var(--font-latin);
}
.auto p { margin: 0; font: 800 var(--fs-strong)/1.3 var(--font); white-space: nowrap; }
@keyframes breathe {
  from { box-shadow: 0 8px 18px -6px rgba(var(--c-900-rgb), 0.45), 0 0 0 0 rgba(var(--c-500-rgb), 0.55); }
  to { box-shadow: 0 8px 18px -6px rgba(var(--c-900-rgb), 0.45), 0 0 22px 6px rgba(var(--c-500-rgb), 0.7); }
}
/* Lands with a bounce: the scale goes on its own property, the centering stays on the transform. */
.alert-enter-active { transition: opacity var(--dur-fast), scale var(--dur-slow) var(--ease-pop); transform-origin: 50% 100%; }
.alert-enter-from { opacity: 0; scale: 0.6; }
</style>
