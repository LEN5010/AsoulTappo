<script setup lang="ts">
// A game under way in the room, on a strip of the mat as the open tables are: its three seats (a seat whose member is
// not in the room shows as a plain disc), its stake as a chip after them where the server says it (ddz_live `base`), and the
// key that watches it.
import { computed } from "vue";
import { members, shownNick } from "../../stores/room";
import { ddzLiveBase, ddzWatch, watchDdz } from "../../stores/ddz";
import { openDdzWindow } from "../../stores/ui";
import DdzSeats from "./DdzSeats.vue";

const props = defineProps<{ table: string; ids: string[] }>();
/** The game watched already: its window comes up, watched from the same seat. */
function watch() {
  if (ddzWatch.value?.id === props.table && !ddzWatch.value.ended) void openDdzWindow();
  else watchDdz(props.table);
}
const seats = computed(() => props.ids.map((id) => {
  const m = members.get(id);
  return m ? { character: m.character, nick: shownNick(m) } : "other" as const;
}));
</script>

<template>
  <div class="row">
    <DdzSeats :seats="seats" :size="36" :stake="ddzLiveBase[table]" />
    <button type="button" class="ui-btn white" @click="watch">观战</button>
  </div>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 14px; }
.row .seats { flex: 0 1 auto; margin-right: auto; }
.ui-btn { flex: none; height: 38px; min-width: 76px; padding: 0 16px; }
.ui-btn.white { --key-lip: var(--c-700); color: var(--c-800); }
</style>
