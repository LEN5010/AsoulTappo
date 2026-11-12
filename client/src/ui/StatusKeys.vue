<script setup lang="ts">
// The room statuses as flat tiles on the paper, three to a row with the name under the icon, and "none" as a line
// of its own below them; with `row`, all of them in one row that fills the width, "none" last. The chosen one is
// tinted coral.
import { ref } from "vue";
import { ROOM_STATUSES } from "../roomStatus";
import { arrowSelect } from "./focus";
import Icon from "./Icon.vue";

defineProps<{ modelValue: string; row?: boolean }>();
defineEmits<{ "update:modelValue": [id: string] }>();

const root = ref<HTMLElement>();
</script>

<template>
  <div ref="root" class="keys" :class="{ row }" role="radiogroup" aria-label="我的状态" @keydown="arrowSelect($event, root)">
    <div class="grid">
      <button
        v-for="k in ROOM_STATUSES" :key="k.id" type="button" role="radio" class="tile" :class="{ on: k.id === modelValue }"
        :aria-checked="k.id === modelValue" @click="$emit('update:modelValue', k.id)"
      >
        <Icon :name="k.icon" :size="20" />
        <span>{{ k.label }}</span>
      </button>
    </div>
    <button
      type="button" role="radio" class="none" :class="{ on: modelValue === '' }" :aria-checked="modelValue === ''"
      @click="$emit('update:modelValue', '')"
    >
      <Icon name="off" :size="row ? 20 : 14" />
      <span>不显示</span>
    </button>
  </div>
</template>

<style scoped>
.keys {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 216px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--c-100);
}
.tile,
.none {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--ink-2);
  font: 700 var(--fs-label)/1 var(--font);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.tile {
  flex-direction: column;
  gap: 6px;
  height: 56px;
}
.none {
  gap: 5px;
  height: 30px;
}
.tile:hover,
.none:hover {
  background: var(--c-50);
  color: var(--ink);
}
.tile.on,
.none.on {
  background: var(--c-100);
  color: var(--c-700);
}
.tile:active,
.none:active {
  background: var(--c-200);
}
/* One row of seven equal tiles; a hairline sets "none" apart. */
.keys.row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  width: auto;
}
.keys.row .grid {
  display: contents;
}
.keys.row .none {
  position: relative;
  flex-direction: column;
  gap: 6px;
  height: 56px;
}
.keys.row .none::before {
  content: "";
  position: absolute;
  left: -3px;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: var(--c-100);
}
.tile:focus-visible,
.none:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: -2px;
}
</style>
