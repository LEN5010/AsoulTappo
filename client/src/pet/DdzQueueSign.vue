<script setup lang="ts">
// Over the own pet while this save waits in the dou dizhu queue: a small paper sign, as over the pet of a member who
// opened a table (DdzSign.vue), with the time waited and a key that stops waiting. Pressing the sign itself brings up
// the lobby (the table's window).
import { ddzQueue, unqueueDdz } from "../stores/ddz";
import { openDdzWindow } from "../stores/ui";
import { useWaited } from "../panel/ddz/waited";
import Icon from "../ui/Icon.vue";

const waited = useWaited(() => ddzQueue.value?.since);
</script>

<template>
  <div class="sign" data-hit role="status">
    <button type="button" class="open" aria-label="斗地主" @click="openDdzWindow()">
      <i class="dot" aria-hidden="true"></i>匹配中<b>{{ waited }}</b>
    </button>
    <button type="button" class="stop" title="取消" aria-label="取消" @click="unqueueDdz"><Icon name="close" :size="12" /></button>
  </div>
</template>

<style scoped>
/* The open table's sign, with the stake's place taken by the time and a cancel key after a thin rule. */
.sign {
  position: absolute;
  left: 50%;
  bottom: 100%;
  translate: -50% -6px;
  display: inline-flex;
  align-items: center;
  height: 26px;
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 0 0 1.5px var(--c-300), 0 6px 14px -6px rgba(var(--c-900-rgb), 0.55);
  white-space: nowrap;
}
.sign button { border: 0; background: none; padding: 0; cursor: pointer; font: inherit; }
.sign .open {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 100%;
  padding: 0 8px 0 10px;
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--c-700);
}
.open b { font: 800 13px/1 var(--font-latin); color: var(--ink-2); font-variant-numeric: tabular-nums; }
/* A coral dot that breathes while it waits. */
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--c-500); animation: wait 1.6s var(--ease-in-out) infinite; }
@keyframes wait {
  50% { opacity: 0.3; }
}
.sign .stop {
  display: grid;
  place-items: center;
  width: 26px;
  height: 100%;
  border-left: 1.5px solid var(--c-200);
  color: var(--ink-2);
}
.sign .stop:hover { color: var(--c-700); }
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
@media (prefers-reduced-motion: reduce) {
  .dot { animation: none; }
}
</style>
