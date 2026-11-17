<script lang="ts">
/** The bubble's size, for keeping it on screen (duelPick.ts, bubblePlacement). */
export const RACE_WIDTH = 204;
export const RACE_HEIGHT = 52;
</script>

<script setup lang="ts">
// Over the own pet when a dumpling race starts, while the reminder is on (settings.raceRemind, the race page's
// switch): one line and the key that opens the race's window (stores/ui.ts, openRaceWindow). The race is followed
// quietly (raceFeed.ts): one question at its start and one at its end. Each race is told once, for a while, and only
// as it starts: an app opened in the middle of one says nothing. While [paused] (another bubble holds the spot)
// it waits.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRaceFeed } from "../panel/park/raceFeed";
import { economy } from "../stores/economy";
import { noPark } from "../stores/park";
import { online } from "../stores/player";
import { settings } from "../stores/settings";
import { openRaceWindow } from "../stores/ui";
import PetBubble from "./PetBubble.vue";

const props = defineProps<{ shift: number; below: boolean; paused?: boolean }>();

/** How long the bubble stays, ms. */
const SHOW_MS = 15_000;
/** A race seen later than this after its start is not told, ms. */
const FRESH_MS = 30_000;

const feed = useRaceFeed({ quiet: true });
const on = computed(() => settings.raceRemind && online.value && !noPark.value && !!economy.value?.park?.race);
watch(on, (is) => (is ? feed.start() : feed.stop()), { immediate: true });

const told = ref(0);
const up = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;
watch(() => (feed.live.value ? feed.race.value : null), (r) => {
  if (!r || r.id === told.value || feed.serverNow.value - r.startsAt * 1000 > FRESH_MS) return;
  told.value = r.id;
  up.value = true;
  clearTimeout(timer);
  timer = setTimeout(() => (up.value = false), SHOW_MS);
});
// The reminder switched off takes the bubble down with it.
watch(on, (is) => { if (!is) up.value = false; });
onBeforeUnmount(() => {
  clearTimeout(timer);
  feed.stop();
});

function watchRace() {
  up.value = false;
  openRaceWindow();
}
</script>

<template>
  <PetBubble :open="up && !props.paused" :width="RACE_WIDTH" :shift="shift" :below="below">
    <div class="race" role="status">
      <p>团子赛跑开赛了</p>
      <button type="button" class="ui-btn small primary" @click="watchRace">观赛</button>
    </div>
  </PetBubble>
</template>

<style scoped>
.race { display: flex; align-items: center; gap: 8px; min-height: 28px; }
.race p { flex: 1; min-width: 0; margin: 0; font: 700 var(--fs-label)/1.4 var(--font); white-space: nowrap; }
</style>
