<script setup lang="ts">
import { computed } from "vue";
import type { Item } from "../items";
import ItemArt from "./ItemArt.vue";
import Icon from "./Icon.vue";

const props = withDefaults(defineProps<{
  item: Item;
  locked?: boolean;
  equipped?: boolean;
  fresh?: boolean;
  count?: number;
  /** shown instead of the name line (e.g. a craft cost) */
  note?: string;
  selected?: boolean;
  size?: number;
}>(), { locked: false, equipped: false, fresh: false, count: 0, note: "", selected: false, size: 96 });
defineEmits<{ click: [] }>();

const rarity = computed(() => props.item.rarity ?? "none");
</script>

<template>
  <button
    type="button" class="item" :class="[`r-${rarity}`, { locked, equipped, selected }]"
    :style="{ width: `${size}px` }" :title="locked ? `未获得：${item.name}` : item.name" @click="$emit('click')"
  >
    <span class="tile" :style="{ height: `${size}px` }">
      <ItemArt :item="item" :size="size - 12" :locked="locked" />
      <span v-if="fresh && !locked" class="fresh">NEW</span>
      <span v-if="count > 1 && !locked" class="count">×{{ count }}</span>
      <span v-if="equipped" class="on"><Icon name="check" :size="12" /></span>
      <span v-if="locked" class="lock"><Icon name="lock" :size="14" /></span>
    </span>
    <span class="name">{{ note || (locked ? "???" : item.name) }}</span>
  </button>
</template>

<style scoped>
.item { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 0; border: none; background: none; cursor: pointer; font: inherit; color: var(--ink); }
/* flat tile; the bottom edge carries the rarity colour */
.tile {
  position: relative; width: 100%; box-sizing: border-box; display: grid; place-items: center; overflow: hidden;
  border-radius: var(--r-l); background: var(--rar-none-bg); box-shadow: inset 0 0 0 1px var(--line);
  transition: box-shadow 120ms;
}
.tile::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: transparent; }
.r-common .tile { background: var(--rar-common-bg); } .r-common .tile::after { background: var(--rar-common); }
.r-rare .tile { background: var(--rar-rare-bg); } .r-rare .tile::after { background: var(--rar-rare); }
.r-epic .tile { background: var(--rar-epic-bg); } .r-epic .tile::after { background: var(--rar-epic); }
.r-legendary .tile { background: var(--rar-legendary-bg); } .r-legendary .tile::after { background: var(--rar-legendary); }
.item:hover .tile { box-shadow: inset 0 0 0 1px var(--line-2); }
.equipped .tile, .selected .tile { box-shadow: inset 0 0 0 2px var(--accent); }
.locked .tile { background: var(--paper-2); }
.locked .tile::after { background: transparent; }
.fresh { position: absolute; left: 5px; top: 5px; font-size: 9px; font-weight: 800; letter-spacing: 0.04em; padding: 1px 4px; border-radius: 3px; background: var(--accent); color: var(--on-accent); }
.count { position: absolute; right: 5px; bottom: 7px; font-size: 10px; font-weight: 700; padding: 0 4px; border-radius: 3px; background: rgba(43, 35, 38, 0.7); color: #fff; font-variant-numeric: tabular-nums; }
.on { position: absolute; right: 5px; top: 5px; width: 18px; height: 18px; border-radius: var(--r-s); display: grid; place-items: center; background: var(--accent); color: var(--on-accent); }
.lock { position: absolute; right: 6px; top: 6px; color: var(--ink-3); }
.name { max-width: 100%; font-size: 12px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink-2); }
.locked .name { color: var(--ink-3); }
</style>
