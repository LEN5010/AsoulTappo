<script setup lang="ts">
// Three seats in a row, each a round face with a name tag: who is at a table, or about to be. An empty seat is a
// dashed ring (a key when [pick] is listened to) over a blank tag; a seat offered to someone from the queue turns its
// ring slowly; a seat that accepted an invite gets a tick. With [stake], the table's base follows them past a rule,
// as a chip the size of a face.
import { characterColor } from "../../manifest";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";
import Icon from "../../ui/Icon.vue";

defineProps<{
  /** null for a seat nobody has yet, "pending" for one offered to someone from the queue. */
  seats: ({ character: string; nick: string; ticked?: boolean } | null | "pending")[];
  /** Diameter of a face, px. */
  size?: number;
  /** Faces only. */
  bare?: boolean;
  /** Empty seats are keys (emitting pick). */
  pickable?: boolean;
  /** The table's base, shown after the seats. */
  stake?: number;
}>();
const emit = defineEmits<{ pick: [seat: number, event: MouseEvent]; press: [] }>();
const face = (s: unknown) => (s && s !== "pending" ? (s as { character: string; nick: string; ticked?: boolean }) : null);
</script>

<template>
  <div class="seats" :class="{ bare }" :style="{ '--d': `${size ?? 56}px` }">
    <div v-for="(s, i) in seats" :key="i" class="seat" :class="{ empty: !face(s), pending: s === 'pending', ticked: face(s)?.ticked }">
      <button
        v-if="pickable && !s" type="button" class="face" aria-label="入座"
        @pointerdown="emit('press')" @click="emit('pick', i, $event)"
      ></button>
      <span v-else class="face"><CharacterAvatar v-if="face(s)" :character="face(s)!.character" :size="size ?? 56" /></span>
      <div v-if="face(s) && !bare" class="tag">
        <i :style="{ background: characterColor(face(s)!.character) }" aria-hidden="true"></i><span>{{ face(s)!.nick }}</span>
      </div>
      <div v-else-if="!bare" class="tag blank" aria-hidden="true"></div>
    </div>
    <template v-if="stake !== undefined">
      <i class="rule" aria-hidden="true"></i>
      <div class="seat of-stake">
        <span class="chip" :class="{ long: stake >= 1000 }">{{ stake.toLocaleString("en-US") }}</span>
        <div v-if="!bare" class="tag"><Icon name="shard" :size="11" /><span>底分</span></div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.seats { display: flex; align-items: flex-start; justify-content: center; gap: 4px; min-width: 0; }
/* A seat is as wide as a name of five or six characters, and gives way to a shorter one where the row is narrow. */
.seat { position: relative; flex: 0 1 auto; width: calc(var(--d) + 56px); min-width: calc(var(--d) + 16px); display: flex; flex-direction: column; align-items: center; gap: 6px; }
.seat.of-stake { flex: none; width: max(calc(var(--d) + 14px), 62px); min-width: 0; }
.bare { gap: 6px; }
.bare .seat { flex: none; width: auto; min-width: 0; }
.face {
  position: relative;
  display: block;
  width: var(--d);
  height: var(--d);
  padding: 0;
  border-radius: 50%;
  box-shadow: 0 0 0 3px #fff, 0 4px 10px -3px rgba(var(--c-900-rgb), 0.5);
}
.bare .face { box-shadow: 0 0 0 2px #fff; }
/* White under the face's own tint, which is see-through. */
.face { background: #fff; }
.face > * { border-radius: 50%; }
.empty .face { background: none; box-shadow: none; border: 2px dashed rgba(255, 255, 255, 0.75); box-sizing: border-box; }
/* An empty seat to sit at: the ring fills a little under the pointer and lifts, as a key does. */
button.face { cursor: pointer; transition: translate var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out); }
button.face:hover { translate: 0 -2px; background: rgba(255, 255, 255, 0.18); }
button.face:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
/* Offered to someone from the queue: the ring turns while it waits for the answer. */
.pending .face { border-color: rgba(255, 255, 255, 0.55); animation: wait 6s linear infinite; }
@keyframes wait {
  to { rotate: 1turn; }
}
@media (prefers-reduced-motion: reduce) {
  .pending .face { animation: none; }
}
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
.tag :deep(svg) { flex: none; color: var(--c-600); }
/* An empty seat: the room of a name, see-through. */
.tag.blank { width: var(--d); background: rgba(255, 255, 255, 0.26); box-shadow: none; }
/* The stake: past a rule as tall as a face, a chip of the table (white, a dashed coral ring inside its edge). */
.rule { flex: none; width: 2px; height: calc(var(--d) * 0.72); margin: calc(var(--d) * 0.14) 6px 0; border-radius: 1px; background: rgba(255, 255, 255, 0.45); }
.chip {
  position: relative;
  display: grid;
  place-items: center;
  width: var(--d);
  height: var(--d);
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 0 3px #fff, 0 4px 10px -3px rgba(var(--c-900-rgb), 0.5);
  color: var(--c-700);
  font: 800 calc(var(--d) * 0.4) / 1 var(--font-latin);
  letter-spacing: -0.3px;
}
.chip.long { font-size: calc(var(--d) * 0.3); }
.chip::before { content: ""; position: absolute; inset: 1px; border-radius: 50%; border: 2px dashed var(--c-300); }
.bare .chip { box-shadow: 0 0 0 2px #fff; }
.tag span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
</style>
