<script setup lang="ts">
// Three seats in a row, each a round face with a name tag: who is at a table, or about to be. An empty seat is a
// dashed ring; a seat that accepted an invite gets a tick.
import { characterColor } from "../../manifest";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";

defineProps<{
  /** null for a seat nobody has yet. */
  seats: ({ character: string; nick: string; ticked?: boolean } | null)[];
  /** Diameter of a face, px. */
  size?: number;
  /** Faces only. */
  bare?: boolean;
}>();
</script>

<template>
  <div class="seats" :class="{ bare }" :style="{ '--d': `${size ?? 56}px` }">
    <div v-for="(s, i) in seats" :key="i" class="seat" :class="{ empty: !s, ticked: s?.ticked }">
      <span class="face"><CharacterAvatar v-if="s" :character="s.character" :size="size ?? 56" /></span>
      <div v-if="s && !bare" class="tag">
        <i :style="{ background: characterColor(s.character) }" aria-hidden="true"></i><span>{{ s.nick }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.seats { display: flex; align-items: flex-start; justify-content: center; gap: 8px; }
.seat { position: relative; width: calc(var(--d) + 48px); display: flex; flex-direction: column; align-items: center; gap: 5px; }
.bare { gap: 6px; }
.bare .seat { width: auto; }
.face {
  position: relative;
  display: block;
  width: var(--d);
  height: var(--d);
  border-radius: 50%;
  box-shadow: 0 0 0 3px #fff, 0 4px 10px -3px rgba(var(--c-900-rgb), 0.5);
}
.bare .face { box-shadow: 0 0 0 2px #fff; }
/* White under the face's own tint, which is see-through. */
.face { background: #fff; }
.face > * { border-radius: 50%; }
.empty .face { background: none; box-shadow: none; border: 2px dashed rgba(255, 255, 255, 0.75); box-sizing: border-box; }
/* Accepted: a tick on the face. */
.ticked .face::after {
  content: "";
  position: absolute;
  right: -3px;
  bottom: -3px;
  width: 36%;
  min-width: 14px;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--ok) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 4.5L19 7.5'/%3E%3C/svg%3E") center / 62% no-repeat;
  box-shadow: 0 0 0 2px #fff;
  animation: tick 240ms var(--ease-pop);
}
@keyframes tick {
  from { scale: 0; }
}
.tag {
  display: flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  height: 20px;
  padding: 0 9px;
  box-sizing: border-box;
  border-radius: 10px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 4px 10px -4px rgba(var(--c-900-rgb), 0.45);
  font: 800 11px/1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.tag i { flex: none; width: 4px; height: 10px; border-radius: 1px; }
.tag span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
</style>
