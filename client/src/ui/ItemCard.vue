<script setup lang="ts">
import { computed } from "vue";
import type { Item, ItemKind } from "../items";
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

const KIND_ICON: Record<ItemKind, string> = {
  character: "person", accessory: "bow", emote: "smile", card: "card", theme: "palette", frame: "ring", badge: "medal",
};
const rarity = computed(() => props.item.rarity ?? "none");
</script>

<template>
  <button
    type="button" class="item" :class="[`r-${rarity}`, { locked, equipped, selected }]"
    :style="{ width: `${size}px` }" :title="locked ? `未获得：${item.name}` : item.name" @click="$emit('click')"
  >
    <span class="tile" :style="{ height: `${size}px` }">
      <ItemArt :item="item" :size="size - 12" :locked="locked" />
      <span class="kind"><Icon :name="KIND_ICON[item.kind]" :size="12" /></span>
      <span v-if="fresh && !locked" class="fresh">NEW</span>
      <span v-if="count > 1 && !locked" class="count">×{{ count }}</span>
      <span v-if="equipped" class="on"><Icon name="check" :size="12" /></span>
      <span v-if="locked" class="lock"><Icon name="lock" :size="14" /></span>
    </span>
    <span class="name">{{ note || (locked ? "???" : item.name) }}</span>
  </button>
</template>

<style scoped>
.item { display: flex; flex-direction: column; align-items: center; gap: 5px; padding: 0; border: none; background: none; cursor: pointer; font: inherit; color: var(--ink); }
.tile {
  position: relative; width: 100%; box-sizing: border-box; display: grid; place-items: center; border-radius: 20px;
  background: var(--rar-none-bg); box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.8), 0 2px 6px rgba(70, 35, 45, 0.1);
  transition: transform 140ms, box-shadow 140ms;
}
.r-common .tile { background: var(--rar-common-bg); }
.r-rare .tile { background: var(--rar-rare-bg); }
.r-epic .tile { background: var(--rar-epic-bg); }
.r-legendary .tile { background: var(--rar-legendary-bg); box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.9), 0 0 0 2px rgba(233, 178, 58, 0.45), 0 4px 14px rgba(233, 178, 58, 0.35); }
.item:hover .tile { transform: translateY(-2px); box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.9), 0 6px 14px rgba(70, 35, 45, 0.16); }
.equipped .tile, .selected .tile { box-shadow: 0 0 0 3px var(--accent), 0 6px 14px rgba(var(--accent-rgb), 0.3); }
.locked .tile { background: var(--paper-2); }
.kind { position: absolute; left: 6px; bottom: 6px; width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; background: rgba(255, 255, 255, 0.85); color: var(--ink-2); }
.fresh { position: absolute; left: 6px; top: 6px; font-size: 9px; font-weight: 800; letter-spacing: 0.04em; padding: 1px 6px; border-radius: 999px; background: var(--accent); color: var(--on-accent); }
.count { position: absolute; right: 6px; bottom: 6px; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 999px; background: rgba(59, 45, 51, 0.72); color: #fff; }
.on { position: absolute; right: 6px; top: 6px; width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: var(--on-accent); }
.lock { position: absolute; right: 7px; top: 7px; color: var(--ink-3); }
.name { max-width: 100%; font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink-2); }
.locked .name { color: var(--ink-3); }
</style>
