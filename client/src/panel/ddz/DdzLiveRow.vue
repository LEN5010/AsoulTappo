<script setup lang="ts">
// A game under way in the room, a row of the table list: its three seats (a seat whose member is not in the room shows
// as a plain disc) with the landlord crowned and the cards each has left, the stake, the multiplier so far and how many
// watch where the server says (ddz_live `base`, ddz_live_state), and the key that watches it.
import { computed } from "vue";
import { members, shownNick } from "../../stores/room";
import { ddzLiveBase, ddzLiveState, ddzWatch, watchDdz } from "../../stores/ddz";
import { openDdzWindow } from "../../stores/ui";
import Icon from "../../ui/Icon.vue";
import DdzRowSeats, { type RowSeat } from "./DdzRowSeats.vue";

const props = defineProps<{ table: string; ids: string[] }>();
/** The game watched already: its window comes up, watched from the same seat. */
function watch() {
  if (ddzWatch.value?.id === props.table && !ddzWatch.value.ended) void openDdzWindow();
  else watchDdz(props.table);
}
const seats = computed<RowSeat[]>(() => props.ids.map((id) => {
  const m = members.get(id);
  return m ? { character: m.character, nick: shownNick(m) } : "other";
}));
const state = computed(() => ddzLiveState.value[props.table]);
const base = computed(() => ddzLiveBase.value[props.table]);
</script>

<template>
  <div class="row">
    <DdzRowSeats :seats="seats" :lord="state?.landlord" :left="state?.left" />
    <div class="meta">
      <span v-if="base !== undefined" class="stake" aria-label="底分"><Icon name="shard" :size="12" /><b>{{ base.toLocaleString("en-US") }}</b></span>
      <b v-if="state" class="mult" aria-label="倍数">×{{ state.mult }}</b>
      <span v-if="state?.watching" class="watching" aria-label="观众"><Icon name="eye" :size="13" />{{ state.watching }}</span>
    </div>
    <button type="button" class="ui-btn" @click="watch">观战</button>
  </div>
</template>

<style scoped src="./tableRow.css"></style>
