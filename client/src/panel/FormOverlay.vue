<script setup lang="ts">
// The second picture of a two-form skin, laid over a still of the first one wherever that is drawn with
// `object-fit: contain` in a box of its own (the draw spotlight). The moving part plays as on the desktop (PetView.vue);
// here everything is in shares of the picture, so the box may be any size.
import { computed } from "vue";
import { getCharacter } from "../characters";

const props = defineProps<{ name: string; on: boolean }>();
const form = computed(() => getCharacter(props.name)?.form);
const loop = computed(() => {
  const l = form.value?.loop;
  if (!l) return null;
  const pct = (v: number, of: number) => `${(v / of) * 100}%`;
  return {
    src: l.src,
    behind: !!l.behind,
    summon: l.entrance === "summon",
    fit: { "--ar": l.width / l.height },
    box: {
      left: pct(l.x, l.width), top: pct(l.y, l.height), width: pct(l.w, l.width), height: pct(l.h, l.height),
      "--loop-steps": l.frames, "--loop-dur": `${l.frames * l.ms}ms`,
    },
  };
});
</script>

<template>
  <span v-if="form" class="form-overlay" :class="{ on }" aria-hidden="true">
    <span v-if="loop?.behind" class="fit" :style="loop.fit">
      <span class="loop" :class="{ summon: loop.summon }" :style="loop.box"><img :src="loop.src" alt="" draggable="false" /></span>
    </span>
    <img class="second" :src="form.bg" alt="" draggable="false" />
    <span v-if="loop && !loop.behind" class="fit" :style="loop.fit">
      <span class="loop" :class="{ summon: loop.summon }" :style="loop.box"><img :src="loop.src" alt="" draggable="false" /></span>
    </span>
  </span>
</template>

<style scoped>
.form-overlay {
  position: absolute;
  inset: 0;
  container-type: size;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-slow) var(--ease-out);
}
.form-overlay.on {
  opacity: 1;
}
.second {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
/* The picture's own box inside the one it is fitted into. */
.fit {
  position: absolute;
  left: 50%;
  top: 50%;
  width: min(100cqw, 100cqh * var(--ar));
  aspect-ratio: var(--ar);
  translate: -50% -50%;
}
.loop {
  position: absolute;
  overflow: hidden;
}
.loop img {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  will-change: transform;
  animation: loop-steps var(--loop-dur) steps(var(--loop-steps)) infinite;
}
@keyframes loop-steps {
  to { transform: translateX(-100%); }
}
/* A summoned loop spins up from a point, overbright, as the second form comes on (PetView.vue). */
.form-overlay.on .loop.summon {
  animation: loop-summon 680ms var(--ease-out) both;
}
@keyframes loop-summon {
  0% { opacity: 0; transform: scale(0.15) rotate(-150deg); filter: brightness(2.6); }
  50% { opacity: 1; transform: scale(1.1) rotate(8deg); filter: brightness(1.6); }
  100% { opacity: 1; transform: scale(1) rotate(0deg); filter: brightness(1); }
}
</style>
