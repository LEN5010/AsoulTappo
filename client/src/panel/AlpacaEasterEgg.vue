<script setup lang="ts">
import { onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { silly } from "../audio/sfx";
import EmoteBubble from "../pet/EmoteBubble.vue";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";
import { alpacaLine } from "../stores/alpaca";
import { reducedMotion } from "../stores/theme";
import { ACHAO } from "../ui/achao";

const emotes = Object.entries(ACHAO).map(([name, src]) => ({ src, name }));
const shown = ref<(typeof emotes)[number] | null>(null);
const frame = ref<EmoteFrame | null>(null);
const player = new EmotePlayer((value) => (frame.value = value), () => 2500);

function surprise() {
  silly();
  said.value = "";
  shown.value = emotes[Math.floor(Math.random() * emotes.length)]!;
  player.play(shown.value.src);
}

// ---- lines handed to it by a page (see stores/alpaca.ts): a hop, a noise and a speech bubble for a few seconds
const SAY_MS = 3600;
const said = ref("");
const button = ref<HTMLButtonElement>();
let hush: ReturnType<typeof setTimeout> | undefined;
watch(alpacaLine, (line) => {
  if (!line) return;
  silly();
  player.clear();
  said.value = line.text;
  clearTimeout(hush);
  hush = setTimeout(() => (said.value = ""), SAY_MS);
  if (reducedMotion.value) return;
  button.value?.animate([
    { transform: "rotate(-5deg)" },
    { transform: "rotate(-5deg) translateY(-12px) scale(1.04, 0.96)", offset: 0.4 },
    { transform: "rotate(-5deg) translateY(0) scale(0.96, 1.04)", offset: 0.7 },
    { transform: "rotate(-5deg)" },
  ], { duration: 460, easing: "ease-out" });
});
function quiet() {
  player.clear();
  clearTimeout(hush);
  said.value = "";
}
onBeforeUnmount(quiet);
onDeactivated(quiet);
</script>

<template>
  <div class="alpaca">
    <button ref="button" type="button" class="alpaca-button" aria-label="戳戳阿草" @click="surprise"></button>
    <div class="bubble-anchor">
      <EmoteBubble :frame="frame" :src="shown?.src" :alt="shown?.name" :anchor="{ x: 0, y: 0 }" :size="76" />
    </div>
    <div class="say-anchor" role="status">
      <Transition name="say">
        <p v-if="said" :key="alpacaLine?.at" class="say">{{ said }}</p>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.alpaca-button {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: url("../assets/brand/side-alpaca.webp") center / contain no-repeat;
  filter: var(--contour) drop-shadow(0 4px 7px rgba(var(--shadow-rgb), .3));
  transform: rotate(-5deg);
  transform-origin: 50% 100%;
  transition: transform var(--dur-slow) var(--ease-spring);
  cursor: pointer;
}
.alpaca-button:hover { transform: rotate(0deg) translateX(5px); }
.alpaca-button:active { transform: rotate(-8deg) scale(.94); }
.alpaca-button:focus-visible { outline: 2px solid var(--ink); outline-offset: -5px; border-radius: var(--radius-l); }
/* A line of speech: white paper up to the right of the head, running out over the page, its tail toward the alpaca. */
.say-anchor {
  position: absolute;
  z-index: 3;
  left: 70%;
  top: 6%;
  width: 0;
  height: 0;
  pointer-events: none;
}
.say {
  position: absolute;
  left: 0;
  bottom: 0;
  margin: 0;
  padding: 8px 13px;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4);
  font: 800 var(--fs-strong)/1.3 var(--font);
  color: var(--ink);
  white-space: nowrap;
  transform-origin: 0 100%;
}
.say::after {
  content: "";
  position: absolute;
  left: 12px;
  top: 100%;
  border-right: 10px solid transparent;
  border-top: 9px solid var(--surface);
}
.say-enter-active {
  animation: say-in 380ms var(--ease-pop);
}
.say-leave-active {
  transition: opacity var(--dur-base) var(--ease-in);
}
.say-leave-to {
  opacity: 0;
}
@keyframes say-in {
  from { opacity: 0; transform: scale(0.5) translateY(8px); }
}
.bubble-anchor {
  --bubble-max-width: 100px;
  position: absolute;
  z-index: 2;
  left: 62%;
  top: 10%;
  width: 0;
  height: 0;
  pointer-events: none;
}
</style>
