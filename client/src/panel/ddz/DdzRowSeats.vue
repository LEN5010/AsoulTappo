<script setup lang="ts">
// The three seats of a table in a row of the room's table list, on paper: a small round face with the name under it.
// An empty seat is a dashed ring (a key when [pickable]); a seat offered to someone from the queue turns its ring; a seat
// taken by someone not in the room is a plain disc with no name. In a game under way the landlord's face wears a crown,
// which pops on when the bidding ends, and each face carries the cards its seat has left, which swell as they drop.
import { watch } from "vue";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";
import Icon from "../../ui/Icon.vue";
import { bump } from "../../ui/motion";

export type RowSeat = { character: string; nick: string } | null | "pending" | "other";
const props = defineProps<{
  seats: RowSeat[];
  /** The landlord's seat, once known. */
  lord?: number | null;
  /** The cards each seat has left, in a game under way. */
  left?: number[];
  /** Empty seats are keys (emitting pick). */
  pickable?: boolean;
}>();
const emit = defineEmits<{ pick: [seat: number, event: MouseEvent]; press: [] }>();
const face = (s: RowSeat) => (s && s !== "pending" && s !== "other" ? s : null);
const counts: (Element | null)[] = [];
watch(() => props.left?.slice(), (now, was) => {
  now?.forEach((n, i) => { if (was?.[i] !== undefined && n !== was[i]) bump(counts[i]); });
}, { flush: "post" });
</script>

<template>
  <div class="seats">
    <div v-for="(s, i) in seats" :key="i" class="seat" :class="{ empty: !s || s === 'pending', pending: s === 'pending', other: s === 'other' }">
      <button
        v-if="pickable && !s" type="button" class="face" aria-label="入座"
        @pointerdown="emit('press')" @click="emit('pick', i, $event)"
      ></button>
      <span v-else class="face">
        <CharacterAvatar v-if="face(s)" :character="face(s)!.character" :size="30" />
        <Transition name="crown"><i v-if="lord === i" class="crown" aria-label="地主"><Icon name="crown" :size="9" /></i></Transition>
        <b v-if="left?.[i] !== undefined" :ref="(el) => (counts[i] = el as Element | null)" class="left">{{ left[i] }}</b>
      </span>
      <span class="name">{{ face(s)?.nick ?? "" }}</span>
    </div>
  </div>
</template>

<style scoped>
.seats { display: flex; align-items: flex-start; gap: 8px; min-width: 0; }
.seat { flex: 0 1 64px; min-width: 40px; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.face {
  position: relative;
  display: block;
  flex: none;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: 0 0 0 2px var(--surface), 0 0 0 3px var(--c-200);
}
.face > :first-child { border-radius: 50%; }
.empty .face { background: none; box-shadow: none; border: 1.5px dashed var(--c-300); box-sizing: border-box; }
.other .face { background: var(--c-100); box-shadow: none; }
/* An empty seat to sit at: the ring fills a little under the pointer and lifts, as a key does. */
button.face { cursor: pointer; transition: translate var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out); }
button.face:hover { translate: 0 -1px; background: var(--c-50); }
button.face:focus-visible { outline: 2px solid var(--c-500); outline-offset: 2px; }
.pending .face { animation: wait 6s linear infinite; }
@keyframes wait {
  to { rotate: 1turn; }
}
.crown {
  position: absolute;
  top: -5px;
  right: -5px;
  display: grid;
  place-items: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--gold);
  box-shadow: 0 0 0 1.5px var(--surface);
  color: #fff;
}
/* The crown lands when the landlord is known: from nothing, a little past full size, then at rest. */
.crown-enter-active { transition: scale var(--dur-slow) var(--ease-pop), rotate var(--dur-slow) var(--ease-pop), opacity var(--dur-fast); }
.crown-enter-from { scale: 0; rotate: -40deg; opacity: 0; }
/* The cards left: a small white card leaning on the face's foot. */
.left {
  position: absolute;
  right: -8px;
  bottom: -4px;
  min-width: 16px;
  height: 15px;
  padding: 0 3px;
  box-sizing: border-box;
  border-radius: 4px;
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--c-200), 0 2px 4px -2px rgba(var(--shadow-rgb), 0.3);
  color: var(--c-700);
  font: 800 10px/15px var(--font-latin);
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.name {
  max-width: 100%;
  min-height: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 var(--fs-caption)/13px var(--font);
  color: var(--ink-2);
}
</style>
