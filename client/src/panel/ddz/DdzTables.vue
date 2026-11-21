<script setup lang="ts">
// The room's tables under the dou dizhu banner, on paper: the open tables this save may sit down at first, oldest
// first, then the games under way in the order they started. Up to SHOWN rows; the rest fold into a last row that
// unfolds them.
import { computed, ref, watch } from "vue";
import type { DdzOpenTable } from "../../net/protocol";
import Icon from "../../ui/Icon.vue";
import DdzLiveRow from "./DdzLiveRow.vue";
import DdzOpenRow from "./DdzOpenRow.vue";

const SHOWN = 3;
const props = defineProps<{ open: DdzOpenTable[]; live: [string, string[]][] }>();
const unfolded = ref(false);
const rows = computed(() => [
  ...props.open.map((t) => ({ key: `o${t.table}`, open: t, live: null })),
  ...props.live.map(([table, ids]) => ({ key: `l${table}`, open: null, live: { table, ids } })),
]);
const folded = computed(() => (unfolded.value ? 0 : Math.max(0, rows.value.length - SHOWN)));
const shown = computed(() => (folded.value ? rows.value.slice(0, SHOWN) : rows.value));
// Folded again once there is nothing left to fold.
watch(() => rows.value.length <= SHOWN, (few) => { if (few) unfolded.value = false; });
</script>

<template>
  <div class="ui-group ui-frame tables">
    <template v-for="r in shown" :key="r.key">
      <DdzOpenRow v-if="r.open" :table="r.open" />
      <DdzLiveRow v-else-if="r.live" :table="r.live.table" :ids="r.live.ids" />
    </template>
    <button v-if="folded" type="button" class="more" @click="unfolded = true">
      还有 {{ folded }} 局<Icon name="down" :size="13" />
    </button>
    <button v-else-if="unfolded" type="button" class="more" @click="unfolded = false">
      收起<Icon name="down" :size="13" class="up" />
    </button>
  </div>
</template>

<style scoped>
.tables { overflow: hidden; }
.more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  height: 36px;
  padding: 0;
  border: 0;
  background: none;
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--c-700);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out);
}
.more:hover { background: var(--c-50); }
.more:focus-visible { outline: 2px solid var(--c-500); outline-offset: -2px; }
.up { rotate: 180deg; }
</style>
