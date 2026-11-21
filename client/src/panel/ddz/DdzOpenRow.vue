<script setup lang="ts">
// An open table of the room that this save may sit down at, on a strip of the mat: its three seats (an empty one is a
// key that sits there), the stake as a chip after them, and the key that sits at the first empty seat. Sitting is consent and the third to
// sit starts the game, so a press that began on another table, or a click right after this one came up, sits nobody
// (inviteKeys).
import { computed, watch } from "vue";
import type { DdzOpenTable } from "../../net/protocol";
import { shownNick } from "../../stores/room";
import { ddzCanSit, sitDdz } from "../../stores/ddz";
import DdzSeats from "./DdzSeats.vue";
import { inviteKeys } from "./inviteKeys";

const props = defineProps<{ table: DdzOpenTable }>();
const seats = computed(() => props.table.seats.map((s) => (!s ? null : "id" in s ? { character: s.character, nick: shownNick(s) } : "pending" as const)));
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
    <DdzSeats :seats="seats" :size="36" :stake="table.base" :pickable="open" @press="keys.press()" @pick="(i, e) => sit(e, i)" />
    <button type="button" class="ui-btn white" :disabled="!open" @pointerdown="keys.press()" @click="sit($event)">入座</button>
  </div>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 14px; }
.row .seats { flex: 0 1 auto; margin-right: auto; }
.ui-btn { flex: none; height: 38px; min-width: 76px; padding: 0 16px; }
.ui-btn.white { --key-lip: var(--c-700); color: var(--c-800); }
.ui-btn:disabled { --key-top: rgba(255, 255, 255, 0.35); --key-bottom: rgba(255, 255, 255, 0.35); color: rgba(255, 255, 255, 0.9); }
</style>
