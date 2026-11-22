<script setup lang="ts">
// The tile matching prizes (behind the band's info key): one row a level, its number, time and top prize. The level with
// the largest top prize is the gold row.
import { computed } from "vue";
import type { LinkLevel } from "../../stores/economy";
import Icon from "../../ui/Icon.vue";
import { raceClock } from "./raceFeed";
import ParkSheet from "./ParkSheet.vue";

const props = defineProps<{ levels: LinkLevel[]; played: number }>();
defineEmits<{ close: [] }>();

const fmt = (n: number) => n.toLocaleString("en-US");
const top = computed(() => Math.max(0, ...props.levels.map((l) => l.max)));
</script>

<template>
  <ParkSheet title="连连看奖励" @close="$emit('close')">
    <ol class="park-sheet-list single">
      <li
        v-for="(l, i) in levels" :key="i" class="park-sheet-row link-prize"
        :class="{ top: l.max === top, next: i === played }"
      >
        <span class="park-sheet-lead level">{{ i + 1 }}</span>
        <span class="park-sheet-main">
          <b class="time"><Icon name="clock" :size="16" />{{ raceClock(l.seconds) }}</b>
        </span>
        <span class="park-sheet-figure figure"><Icon name="shard" :size="20" />{{ fmt(l.max) }}</span>
      </li>
    </ol>
  </ParkSheet>
</template>

<style scoped>
.level {
  font: 800 26px/1 var(--font-latin);
  color: var(--c-700);
}
.top .level {
  color: color-mix(in oklab, var(--gold) 70%, var(--c-800));
}
.park-sheet-main .time {
  gap: 5px;
  font: 800 20px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}
.time svg {
  color: var(--c-600);
}
.next:not(.top) {
  box-shadow: inset 0 0 0 2px var(--c-300);
}
.figure {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.figure svg {
  color: var(--c-600);
}
.top .figure svg {
  color: color-mix(in oklab, var(--gold) 78%, var(--c-700));
}
</style>
