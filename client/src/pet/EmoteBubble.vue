<script setup lang="ts">
// Speech bubble growing from the upper right of the character's head.
// A new emote swaps the picture inside the open bubble; repeats show ×N.
import { computed } from "vue";
import { emoteView } from "../emotes";
import { serverBase } from "../asset";
import { reducedMotion } from "../stores/theme";
import type { EmoteFrame } from "./EmotePlayer";

const props = defineProps<{
  frame: EmoteFrame | null;
  /** tail tip, px from the canvas top-left */
  anchor: { x: number; y: number };
  /** emote picture height in px */
  size: number;
  /** grow to the upper left instead (pet near the right screen edge) */
  flip?: boolean;
}>();

const view = computed(() =>
  props.frame
    ? emoteView(props.frame.key, {
        serverBase: serverBase.value,
        appBase: import.meta.env.BASE_URL,
      })
    : null,
);
const style = computed(() => ({ left: `${props.anchor.x}px`, top: `${props.anchor.y}px` }));
</script>

<template>
  <div class="anchor" :style="style">
    <Transition :name="reducedMotion ? 'fade' : 'bubble'">
      <div v-if="frame && view?.img" class="bubble" :class="{ flip }">
        <Transition :name="reducedMotion ? 'fade' : 'swap'" mode="out-in">
          <img :key="frame.seq" :src="view.img" :style="{ height: `${size}px` }" alt="" draggable="false" />
        </Transition>
        <span v-if="frame.count > 1" :key="frame.count" class="times">×{{ frame.count }}</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; width: 0; height: 0; pointer-events: none; z-index: 5; }
.bubble {
  position: absolute; left: 0; bottom: 0; transform-origin: 0 100%;
  padding: 6px; border-radius: 16px 16px 16px 4px; background: #FFF9F2;
  box-shadow: 0 4px 14px rgba(72, 38, 20, 0.18), 0 0 0 2px var(--tile-border, #DFC9B0);
}
.bubble::after {
  content: ""; position: absolute; left: -5px; bottom: -3px; width: 14px; height: 12px; background: #FFF9F2;
  clip-path: polygon(0 100%, 100% 0, 100% 70%); border-bottom-left-radius: 4px;
}
.bubble.flip { left: auto; right: 0; transform-origin: 100% 100%; border-radius: 16px 16px 4px 16px; }
.bubble.flip::after { left: auto; right: -5px; clip-path: polygon(100% 100%, 0 0, 0 70%); border-bottom-left-radius: 0; border-bottom-right-radius: 4px; }
.bubble.flip .times { right: auto; left: -8px; }
.bubble img { display: block; width: auto; max-width: 160px; object-fit: contain; }
.times {
  position: absolute; right: -8px; top: -9px; padding: 1px 6px; border-radius: 999px; font-size: 12px; font-weight: 800; font-variant-numeric: tabular-nums;
  background: var(--accent, #FC966E); color: var(--on-accent, #562915); border: 1.5px solid var(--accent-deep, #D26A42); box-shadow: 0 2px 4px rgba(72, 38, 20, 0.18);
  animation: times 260ms cubic-bezier(0.34, 1.8, 0.64, 1);
}
.bubble-enter-active { animation: bubble-in 260ms cubic-bezier(0.34, 1.6, 0.64, 1); }
.bubble-leave-active { transition: opacity 300ms ease-in, transform 300ms ease-in; }
.bubble-leave-to { opacity: 0; transform: translateY(-12px) scale(0.92); }
.swap-enter-active { animation: swap-in 160ms cubic-bezier(0.34, 1.6, 0.64, 1); }
.swap-leave-active { transition: opacity 80ms, transform 80ms; }
.swap-leave-to { opacity: 0; transform: scale(0.8); }
.fade-enter-active, .fade-leave-active { transition: opacity 200ms; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@keyframes bubble-in { from { opacity: 0; transform: scale(0.5) translate(-6px, 8px); } 60% { opacity: 1; transform: scale(1.06); } to { transform: none; } }
@keyframes swap-in { from { opacity: 0; transform: scale(0.75); } to { opacity: 1; transform: none; } }
@keyframes times { from { transform: scale(0.4); } }
</style>
