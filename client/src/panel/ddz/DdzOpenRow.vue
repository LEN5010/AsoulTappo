<script setup lang="ts">
// An open table of the room that this save may sit down at, a row of the table list: its three seats (an empty one is a
// key that sits there), the stake, and the key that sits at the first empty seat. Sitting is consent and the third to
// sit starts the game, so a press that began on another table, or a click right after this one came up, sits nobody
// (inviteKeys).
import { computed, watch } from "vue";
import type { DdzOpenTable } from "../../net/protocol";
import { shownNick } from "../../stores/room";
import { ddzCanSit, sitDdz } from "../../stores/ddz";
import Icon from "../../ui/Icon.vue";
import DdzRowSeats, { type RowSeat } from "./DdzRowSeats.vue";
import { inviteKeys } from "./inviteKeys";

const props = defineProps<{ table: DdzOpenTable }>();
const seats = computed<RowSeat[]>(() => props.table.seats.map((s) => (!s ? null : "id" in s ? { character: s.character, nick: shownNick(s) } : "pending")));
const open = computed(() => ddzCanSit(props.table.base) && props.table.seats.some((s) => !s));
const keys = inviteKeys();
watch(() => props.table.table, (id) => keys.show(id), { immediate: true, flush: "sync" });
function sit(e: MouseEvent, seat?: number) {
  const id = keys.pick(true, e.detail > 0);
  if (id) sitDdz(id, seat);
}
</script>

<template>
  <div class="row">
    <DdzRowSeats :seats="seats" :pickable="open" @press="keys.press()" @pick="(i, e) => sit(e, i)" />
    <div class="meta">
      <span class="stake" aria-label="底分"><Icon name="shard" :size="12" /><b>{{ table.base.toLocaleString("en-US") }}</b></span>
    </div>
    <button type="button" class="ui-btn primary" :disabled="!open" @pointerdown="keys.press()" @click="sit($event)">入座</button>
  </div>
</template>

<style scoped src="./tableRow.css"></style>
