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
  note?: string;
  selected?: boolean;
  size?: number;
}>(), { locked: false, equipped: false, fresh: false, count: 0, note: "", selected: false, size: 112 });
defineEmits<{ click: [] }>();

const rarity = computed(() => props.item.rarity ?? "none");
const badgeIcon = computed(() => {
  if (props.item.kind === "character") return "person";
  if (props.item.kind === "card") return "card";
  return "smile";
});
</script>

<template>
  <button
    type="button" class="sq-card" :class="[`r-${rarity}`, { locked, equipped, selected }]"
    :style="{ width: `${size}px` }" :title="locked ? `未获得：${item.name}` : item.name" @click="$emit('click')"
  >
    <span class="well" :style="{ height: `${size - 16}px` }">
      <ItemArt :item="item" :size="size - 24" :locked="locked" />
      <span class="corner-badge" aria-hidden="true"><Icon :name="badgeIcon" :size="11" /></span>
      <span v-if="fresh && !locked" class="fresh">NEW</span>
      <span v-if="count > 1 && !locked" class="count">×{{ count }}</span>
      <span v-if="equipped" class="on"><Icon name="star" :size="11" /></span>
    </span>
    <span class="name">{{ note || item.name }}</span>
  </button>
</template>

<style scoped>
/* WuwaTappo-inspired squircle card frame with inner pastel window + bottom-left badge + centered title */
.sq-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 7px 7px 9px;
  box-sizing: border-box;
  border-radius: 22px;
  border: 2px solid var(--tile-border);
  background: var(--tile-frame);
  box-shadow: 0 3px 0 var(--tile-lip);
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  transition: transform 140ms cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 140ms, border-color 140ms;
}
.sq-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent);
}
.sq-card.equipped,
.sq-card.selected {
  background: #FFF7EE;
  border-color: var(--accent);
  box-shadow: 0 3px 0 var(--accent-deep), 0 0 12px rgba(var(--accent-rgb), 0.45);
}
.well {
  position: relative;
  width: 100%;
  box-sizing: border-box;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 16px;
  background:
    repeating-linear-gradient(
      -35deg,
      rgba(255, 255, 255, 0.22) 0 10px,
      transparent 10px 22px
    ),
    var(--rar-none-bg);
}
.r-common .well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 10px, transparent 10px 22px),
    var(--rar-common-bg);
}
.r-rare .well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 10px, transparent 10px 22px),
    var(--rar-rare-bg);
}
.r-epic .well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 10px, transparent 10px 22px),
    var(--rar-epic-bg);
}
.r-legendary .well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.25) 0 10px, transparent 10px 22px),
    var(--rar-legendary-bg);
}
.corner-badge {
  position: absolute;
  left: 5px;
  bottom: 5px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--tile-frame);
  border: 1.5px solid var(--tile-border);
  color: #B48967;
  display: grid;
  place-items: center;
}
.fresh {
  position: absolute;
  left: 5px;
  top: 5px;
  font-size: 9px;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--on-accent);
}
.count {
  position: absolute;
  right: 5px;
  top: 5px;
  font-size: 10px;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(92, 59, 40, 0.75);
  color: #FFF9F2;
}
.on {
  position: absolute;
  right: 5px;
  top: 5px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--accent);
  color: var(--on-accent);
  box-shadow: 0 1px 3px rgba(92, 59, 40, 0.25);
}
.name {
  max-width: 100%;
  margin-top: 7px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--ink);
  text-align: center;
}
.locked .name {
  color: var(--ink-3);
}
</style>
