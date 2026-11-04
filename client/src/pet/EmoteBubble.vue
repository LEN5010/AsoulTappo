<script setup lang="ts">
// Die-cut sticker popping up at the upper right of the character's head: the emote with a white
// contour and a shadow so it reads on any wallpaper, plus a small white point aimed at the character.
// A new emote swaps the picture in place; repeats show ×N.
import { computed } from "vue";
import { emoteView } from "../emotes";
import { serverBase } from "../asset";
import { reducedMotion } from "../stores/theme";
import type { EmoteFrame } from "./EmotePlayer";

const props = defineProps<{
  frame: EmoteFrame | null;
  /** tip of the white point, px from the canvas top-left */
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
        <div class="sticker" :style="{ '--size': `${size}px` }">
          <i class="point" />
          <Transition :name="reducedMotion ? 'fade' : 'swap'" mode="out-in">
            <img :key="frame.seq" :src="view.img" :style="{ height: `${size}px` }" alt="" draggable="false" />
          </Transition>
        </div>
        <span v-if="frame.count > 1" :key="frame.count" class="times">×{{ frame.count }}</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; width: 0; height: 0; pointer-events: none; z-index: 5; }
.bubble { position: absolute; left: 0; bottom: 0; transform-origin: 0 100%; }
.bubble.flip { left: auto; right: 0; transform-origin: 100% 100%; }
.bubble.flip .times { right: auto; left: -8px; }
/* The shadow wraps the picture and the point as one shape; the contour stays on the picture
   alone, because its offset passes would fork a sharp tip. */
.sticker {
  --tip: calc(var(--size) * 0.19 - 8px);
  position: relative;
  margin: 0 0 10px calc(var(--tip) * -1);
  filter: drop-shadow(0 1.5px 1.5px rgba(43, 37, 48, 0.38)) drop-shadow(0 4px 7px rgba(43, 37, 48, 0.3));
}
.flip .sticker { margin: 0 calc(var(--tip) * -1) 10px 0; }
/* Sits away from the corner and runs under the picture: every emote reaches the bottom edge of
   its box, but many leave the corner itself empty. */
.point {
  position: absolute;
  left: var(--tip);
  bottom: -10px;
  width: 30px;
  height: 18px;
  background: #fff;
  clip-path: polygon(0 100%, 20% 0, 100% 0);
}
.flip .point { left: auto; right: var(--tip); transform: scaleX(-1); }
.sticker img { position: relative; display: block; width: auto; max-width: 160px; object-fit: contain; filter: var(--contour-lg); }
.times {
  position: absolute; right: -9px; top: -10px; padding: 0 7px; font: italic 800 15px/19px var(--font-latin);
  background: var(--ink); color: #fff; transform: skewX(var(--skew));
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
@keyframes times { from { transform: skewX(var(--skew)) scale(0.4); } }
</style>
