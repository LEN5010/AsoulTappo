<script setup lang="ts">
// Over the pet of a member who opened a dou dizhu table in the room: a small paper sign with the stake and how many
// sit there. Pressing it sits this save down; as on the banner, a press that began on another table, or a click right
// after this one came up, sits nobody (inviteKeys).
import { computed, watch } from "vue";
import type { DdzOpenTable } from "../net/protocol";
import { inviteKeys } from "../panel/ddz/inviteKeys";
import { ddzCanSit, sitDdz } from "../stores/ddz";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ table: DdzOpenTable }>();
const taken = computed(() => props.table.seats.filter((s) => !!s).length);
const open = computed(() => ddzCanSit(props.table.base) && taken.value < 3);
const keys = inviteKeys();
watch(() => props.table.table, (id) => keys.show(id), { immediate: true, flush: "sync" });
function sit(e: MouseEvent) {
  const id = keys.pick(true, e.detail > 0);
  if (id) sitDdz(id);
}
</script>

<template>
  <button
    type="button" class="sign" data-hit data-no-drag :disabled="!open" aria-label="入座"
    @pointerdown="keys.press()" @click="sit"
  >
    <Icon name="shard" :size="12" /><b>{{ table.base.toLocaleString("en-US") }}</b><i>{{ taken }}/3</i>
  </button>
</template>

<style scoped>
/* A white card pinned over the head: the stake in the coral of the mat, the seats taken after a thin rule. */
.sign {
  position: absolute;
  left: 50%;
  bottom: 100%;
  translate: -50% -6px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 26px;
  padding: 0 9px 0 7px;
  border: 0;
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 0 0 1.5px var(--c-300), 0 6px 14px -6px rgba(var(--c-900-rgb), 0.55);
  font: 800 13px/1 var(--font-latin);
  color: var(--c-700);
  white-space: nowrap;
  cursor: pointer;
  transition: translate var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.sign .icon { color: var(--c-500); }
.sign i { margin-left: 4px; padding-left: 6px; border-left: 1.5px solid var(--c-200); font-style: normal; color: var(--ink-2); font-variant-numeric: tabular-nums; }
.sign:hover:not(:disabled) { translate: -50% -8px; box-shadow: 0 0 0 1.5px var(--c-400), 0 8px 16px -6px rgba(var(--c-900-rgb), 0.55); }
.sign:disabled { cursor: default; }
/* A little tail down to the head. */
.sign::after {
  content: "";
  position: absolute;
  left: 50%;
  top: 100%;
  width: 8px;
  height: 8px;
  translate: -50% -4px;
  rotate: 45deg;
  background: var(--surface);
  box-shadow: 1.5px 1.5px 0 0 var(--c-300);
}
</style>
