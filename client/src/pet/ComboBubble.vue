<script setup lang="ts">
import type { ComboFrame } from "./TapCombo";

defineProps<{ frame: ComboFrame | null; x: number; y: number; size: number }>();
</script>

<template>
  <div class="anchor" :style="{ left: `${x}px`, top: `${y}px` }">
    <Transition name="combo">
      <span v-if="frame" :key="frame.seq" class="combo" :style="{ fontSize: `${size}px` }">
        <span :key="frame.beat" class="num">+{{ frame.count }}</span>
      </span>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; width: 0; height: 0; pointer-events: none; z-index: 4; }
.combo { position: absolute; left: 0; bottom: 0; transform: translateX(-50%); white-space: nowrap; }
.num {
  display: inline-block; font-family: var(--font-latin); font-weight: 800; color: var(--c-600);
  -webkit-text-stroke: 4px var(--surface); paint-order: stroke fill; text-shadow: 0 2px 6px rgba(var(--shadow-rgb), 0.25);
  animation: beat var(--dur-base) var(--ease-pop);
}
.combo-enter-active { transition: opacity var(--dur-fast), transform var(--dur-fast); }
.combo-enter-from { opacity: 0; transform: translate(-50%, 8px); }
.combo-leave-active { transition: opacity var(--dur-stage) var(--ease-in), transform var(--dur-stage) var(--ease-in); }
.combo-leave-to { opacity: 0; transform: translate(-50%, -18px); }
@keyframes beat { from { transform: scale(1.35); } }
</style>
