<script setup lang="ts">
// A game under way in the room, on a strip of the mat as the open tables are: its three seats (a seat whose member is
// not in the room shows as a ring) and the key that watches it. The stake is not known before watching (ddz_live
// does not carry it).
import { computed } from "vue";
import { members, shownNick } from "../../stores/room";
import { watchDdz } from "../../stores/ddz";
import DdzSeats from "./DdzSeats.vue";

const props = defineProps<{ table: string; ids: string[] }>();
const seats = computed(() => props.ids.map((id) => {
  const m = members.get(id);
  return m ? { character: m.character, nick: shownNick(m) } : null;
}));
</script>

<template>
  <div class="row">
    <DdzSeats :seats="seats" :size="36" />
    <button type="button" class="ui-btn white" @click="watchDdz(table)">观战</button>
  </div>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 14px; }
.row .seats { flex: 0 1 auto; margin-right: auto; }
.ui-btn { flex: none; height: 38px; min-width: 76px; padding: 0 16px; }
.ui-btn.white { --key-lip: var(--c-700); color: var(--c-800); }
</style>
