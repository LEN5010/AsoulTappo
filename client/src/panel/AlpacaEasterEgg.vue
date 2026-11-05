<script setup lang="ts">
import { onBeforeUnmount, onDeactivated, ref } from "vue";
import EmoteBubble from "../pet/EmoteBubble.vue";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";

const files = import.meta.glob<string>("../assets/emotes/achao/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});
const emotes = Object.entries(files).map(([path, src]) => ({
  src,
  name: path.slice(path.lastIndexOf("/") + 1, -5),
}));
const shown = ref<(typeof emotes)[number] | null>(null);
const frame = ref<EmoteFrame | null>(null);
const player = new EmotePlayer((value) => (frame.value = value), () => 2500);

function surprise() {
  shown.value = emotes[Math.floor(Math.random() * emotes.length)]!;
  player.play(shown.value.src);
}
onBeforeUnmount(() => player.clear());
onDeactivated(() => player.clear());
</script>

<template>
  <div class="alpaca">
    <button type="button" class="alpaca-button" aria-label="戳戳阿草" @click="surprise"></button>
    <div class="bubble-anchor">
      <EmoteBubble :frame="frame" :src="shown?.src" :alt="shown?.name" :anchor="{ x: 0, y: 0 }" :size="76" />
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
  filter: var(--contour) drop-shadow(0 4px 7px rgba(var(--ink-rgb), .3));
  transform: rotate(-5deg);
  transform-origin: 50% 100%;
  transition: transform var(--dur-slow) var(--ease-spring);
  cursor: pointer;
}
.alpaca-button:hover { transform: rotate(0deg) translateX(5px); }
.alpaca-button:active { transform: rotate(-8deg) scale(.94); }
.alpaca-button:focus-visible { outline: 2px solid var(--ink); outline-offset: -5px; border-radius: var(--radius-l); }
.bubble-anchor {
  --bubble-max-width: 100px;
  position: absolute;
  left: 62%;
  top: 10%;
  width: 0;
  height: 0;
  pointer-events: none;
}
</style>
