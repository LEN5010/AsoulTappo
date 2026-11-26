<script setup lang="ts">
// A table of the hall's list in the sheet that starts a game (DdzInvite.vue), as a row of the room's table list: its
// three seats (an empty one is a key that sits there) and the key that sits at the first empty seat. Sitting is consent
// and the third to sit starts the game, so a press that began on another table, or a click right after this one came
// up, sits nobody (inviteKeys).
import { computed, watch } from "vue";
import type { DdzHallTable } from "../../net/protocol";
import { shownNick } from "../../stores/room";
import { sitDdzAt } from "../../stores/ddz";
import DdzRowSeats, { type RowSeat } from "./DdzRowSeats.vue";
import { inviteKeys } from "./inviteKeys";

/** [base]: the stake the table is listed at; [open]: the save may sit down now. */
const props = defineProps<{ table: DdzHallTable; base: number; open: boolean }>();
const emit = defineEmits<{ sat: [] }>();
const seats = computed<RowSeat[]>(() => props.table.seats.map((s) => (!s ? null : "pending" in s ? "pending" : { character: s.character, nick: shownNick(s) })));
const keys = inviteKeys();
watch(() => props.table.table, (id) => keys.show(id), { immediate: true, flush: "sync" });
function sit(e: MouseEvent, seat?: number) {
  const id = keys.pick(true, e.detail > 0);
  if (!id) return;
  sitDdzAt(id, seat, props.base);
  emit("sat");
}
</script>

<template>
  <div class="row">
    <DdzRowSeats :seats="seats" :pickable="open" @press="keys.press()" @pick="(i, e) => sit(e, i)" />
    <button type="button" class="ui-btn primary" :disabled="!open" @pointerdown="keys.press()" @click="sit($event)">入座</button>
  </div>
</template>

<style scoped src="./tableRow.css"></style>
<style scoped>
.row > .ui-btn { margin-left: auto; }
/* Three full seats (64 each) when the row has the room: an empty seat's short content does not narrow the names. */
.row > .seats { flex: 0 1 208px; }
</style>
