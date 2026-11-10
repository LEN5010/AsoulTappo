<script setup lang="ts">
// A paper bubble over a pet that takes the mouse: the duel and its bets. Centered over the pet with its point at the
// head; [shift] moves the paper sideways to stay on screen, [below] puts it under the pet when there is no room above.
withDefaults(defineProps<{ open: boolean; width: number; shift?: number; below?: boolean }>(), { shift: 0, below: false });
</script>

<template>
  <div class="anchor" :class="{ below }">
    <Transition name="pop">
      <div v-if="open" class="bubble" data-hit data-no-drag :style="{ width: `${width}px`, '--shift': `${shift}px` }">
        <slot />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 7; }
.anchor.below { top: 100%; }
.bubble {
  position: absolute; left: 0; bottom: 8px; padding: 8px 10px 10px; box-sizing: border-box;
  transform: translateX(calc(-50% + var(--shift))); border-radius: 14px; background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4); color: var(--ink);
}
.below .bubble { bottom: auto; top: 8px; }
/* The point stays on the pet when the paper shifts. */
.bubble::after {
  content: ""; position: absolute; left: calc(50% - var(--shift)); top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.below .bubble::after { top: auto; bottom: 100%; border: 7px solid transparent; border-bottom-color: var(--surface); border-top: 0; }
.pop-enter-active { transition: opacity var(--dur-fast), scale var(--dur-fast) var(--ease-pop); }
.pop-enter-from { opacity: 0; scale: 0.85; }
.pop-leave-active { transition: opacity var(--dur-base) var(--ease-in); }
.pop-leave-to { opacity: 0; }
</style>
