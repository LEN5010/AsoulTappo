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
  display: inline-block; font-family: var(--font-latin); font-style: italic; font-weight: 800; color: var(--accent);
  -webkit-text-stroke: 4px #fff; paint-order: stroke fill; text-shadow: 0 2px 6px rgba(43, 37, 48, 0.25);
  animation: beat 220ms cubic-bezier(0.34, 1.8, 0.64, 1);
}
.combo-enter-active { transition: opacity 120ms, transform 120ms; }
.combo-enter-from { opacity: 0; transform: translate(-50%, 8px); }
.combo-leave-active { transition: opacity 500ms ease-in, transform 500ms ease-in; }
.combo-leave-to { opacity: 0; transform: translate(-50%, -18px); }
@keyframes beat { from { transform: scale(1.35); } }
</style>
