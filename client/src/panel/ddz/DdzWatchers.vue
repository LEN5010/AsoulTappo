<script setup lang="ts">
// Who watches a dou dizhu table: an eye, the faces of up to three watchers over one another, and how many there are.
// In the table's top bar it is a key that opens a white slip listing the watchers under the seat whose hand each one
// sees (those who see none last); [mini], beside a seat's name, it only shows the faces. The count gives a little
// bounce when it changes, as a seat's cards left do.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { DdzWatchFace } from "../../net/protocol";
import { shownNick } from "../../stores/room";
import { reducedMotion } from "../../stores/theme";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";
import Icon from "../../ui/Icon.vue";

const props = defineProps<{
  faces: DdzWatchFace[];
  /** Beside a seat's name: faces only, no key. */
  mini?: boolean;
  /** The name of seat [seat], heading its watchers on the slip. */
  seatNick?: (seat: number) => string;
  /** The slip opens from the key's right edge (a key on the right of the bar). */
  right?: boolean;
}>();

/** Faces shown over one another; more than that are counted. */
const SHOWN = 3;
const shown = computed(() => props.faces.slice(0, SHOWN));

/** The slip: the watchers by the seat whose hand they see, seats in order, then those who see none. */
const groups = computed(() => {
  const seats = [0, 1, 2, null].map((seat) => ({ seat, faces: props.faces.filter((f) => f.seat === seat) }));
  return seats.filter((g) => g.faces.length);
});

const open = ref(false);
const root = ref<HTMLElement>();
function outside(e: PointerEvent) {
  if (!root.value?.contains(e.target as Node)) open.value = false;
}
watch(open, (on) => {
  if (on) document.addEventListener("pointerdown", outside, true);
  else document.removeEventListener("pointerdown", outside, true);
});
// Nobody left to list: the slip goes.
watch(() => props.faces.length, (n) => { if (!n) open.value = false; });
onBeforeUnmount(() => document.removeEventListener("pointerdown", outside, true));

/** Bumped each time the count changes, so it bounces then (and not on opening). */
const bump = ref(0);
watch(() => props.faces.length, (n, before) => { if (n !== before) bump.value += 1; });
</script>

<template>
  <span v-if="mini" class="watchers mini">
    <Icon name="eye" :size="16" />
    <span class="faces">
      <CharacterAvatar v-for="(f, i) in shown" :key="i" :character="f.character" :size="22" />
    </span>
    <b v-if="faces.length > SHOWN" :key="bump" :class="{ bump: bump && !reducedMotion }">+{{ faces.length - SHOWN }}</b>
  </span>
  <span v-else ref="root" class="watchers" :class="{ right }">
    <button
      type="button" class="ui-btn small ghost" :aria-expanded="open" :aria-label="`${faces.length}`"
      @click="open = !open"
    >
      <Icon name="eye" :size="18" />
      <span class="faces">
        <CharacterAvatar v-for="(f, i) in shown" :key="i" :character="f.character" :size="22" />
      </span>
      <b :key="bump" :class="{ bump: bump && !reducedMotion }">{{ faces.length }}</b>
    </button>
    <div v-if="open" class="slip" role="dialog">
      <section v-for="g in groups" :key="g.seat ?? 'none'">
        <h5 v-if="g.seat !== null && seatNick"><Icon name="eye" :size="13" /><span>{{ seatNick(g.seat) }}</span></h5>
        <ul>
          <li v-for="(f, i) in g.faces" :key="i">
            <CharacterAvatar :character="f.character" :size="28" />
            <span>{{ shownNick(f) }}</span>
          </li>
        </ul>
      </section>
    </div>
  </span>
</template>

<style scoped>
.watchers { position: relative; display: inline-flex; align-items: center; pointer-events: auto; }
.watchers :deep(.icon) { color: var(--c-700); }
/* Faces over one another, each ringed in white. */
.faces { display: flex; align-items: center; }
.faces > * { border-radius: 50%; box-shadow: 0 0 0 2px #fff; background-color: #fff; }
.faces > * + * { margin-left: -7px; }
b { font: 800 18px/1 var(--font-latin); color: var(--c-700); letter-spacing: -0.3px; }
b.bump { animation: bump 520ms var(--ease-out); }
@keyframes bump {
  0% { scale: 0.6; }
  30% { scale: 1.32; }
  55% { scale: 0.92; }
  75% { scale: 1.08; }
  100% { scale: 1; }
}
/* The key in the top bar is as tall as its neighbours. */
.watchers > .ui-btn { height: 36px; padding: 0 12px; gap: 7px; }
/* Beside a name, on a white tag of its own. */
.mini {
  gap: 5px;
  height: 28px;
  padding: 0 9px 0 8px;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 5px 12px -5px rgba(var(--shadow-rgb), 0.3);
  pointer-events: none;
}
.mini b { font-size: 15px; }
/* The list: white paper under the key. */
.slip {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 8;
  min-width: 184px;
  max-width: 260px;
  max-height: 420px;
  overflow-y: auto;
  padding: 8px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.08), 0 16px 32px -14px rgba(var(--c-900-rgb), 0.45);
  animation: open 160ms var(--ease-out);
}
.right .slip { left: auto; right: 0; }
@keyframes open {
  from { opacity: 0; translate: 0 -6px; }
}
.slip section + section { margin-top: 6px; padding-top: 6px; border-top: 2px dashed var(--c-100); }
.slip h5 {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 2px 6px 4px;
  font: 800 var(--fs-label)/1.2 var(--font);
  color: var(--ink-3);
  white-space: nowrap;
}
.slip h5 span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.slip ul { margin: 0; padding: 0; list-style: none; }
.slip li { display: flex; align-items: center; gap: 9px; height: 38px; padding: 0 6px; font: 800 var(--fs-strong)/1 var(--font); color: var(--ink); }
.slip li > :first-child { border-radius: 50%; }
.slip li span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
