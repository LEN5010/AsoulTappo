<script setup lang="ts">
// Backpack filter: a member card narrows the shelves to her, the ALL card lifts the filter.
import { characters } from "../characters";
import { manifest } from "../manifest";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";

defineProps<{ modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [name: string] }>();

const EN_NAMES: Record<string, string> = { jiaran: "Diana", nailin: "Eileen", beila: "Bella", xinyi: "Fiona", sinuo: "Gladys" };
/** Busts stacked as silhouettes on the ALL card, back to front. */
const GHOSTS = manifest.characters.slice(0, 3).flatMap((m) => characters[m.name]?.bg ?? []);

const pick = (name: string) => emit("update:modelValue", name);
</script>

<template>
  <div class="members" role="group" aria-label="筛选成员">
    <button
      type="button" class="member ui-frame" :class="{ on: modelValue === 'all' }"
      :aria-pressed="modelValue === 'all'" title="显示全部成员" @click="pick('all')"
    >
      <span class="ghosts" aria-hidden="true">
        <span class="stack"><PetBust v-for="bg in GHOSTS" :key="bg" class="ghost" :src="bg" /></span>
        <span class="ask">?</span>
      </span>
      <b>全部</b>
      <small>ALL</small>
      <span v-if="modelValue === 'all'" class="mark" aria-hidden="true"><Icon name="check" :size="11" /></span>
    </button>
    <button
      v-for="m in manifest.characters" :key="m.id" type="button"
      class="member ui-frame" :class="{ on: modelValue === m.name }"
      :aria-pressed="modelValue === m.name" :title="`使用${m.name}原皮`" @click="pick(m.name)"
    >
      <PetBust v-if="characters[m.name]" class="bust" :src="characters[m.name]!.bg" />
      <b><i :style="{ background: m.color }" aria-hidden="true"></i>{{ m.name }}</b>
      <small>{{ EN_NAMES[m.id] }}</small>
      <span v-if="modelValue === m.name" class="mark" aria-hidden="true"><Icon name="check" :size="11" /></span>
    </button>
  </div>
</template>

<style scoped>
.members {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
}
.member {
  --radius: var(--radius-s);
  height: 86px;
  padding: 3px 0 6px;
  box-sizing: border-box;
  border: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line);
  color: var(--ink-2);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out);
}
.member:hover {
  transform: translateY(-2px);
}
.member:hover:not(.on) {
  box-shadow: inset 0 0 0 1.5px var(--accent-mid), 0 6px 12px -8px rgba(var(--accent-rgb), 0.7);
}
.member:focus-visible {
  box-shadow: inset 0 0 0 2.5px var(--ink);
}
.member.on {
  background: var(--grad-main);
  box-shadow: var(--glow-m);
  color: var(--on-accent-surface);
}
.bust {
  flex: none;
  width: 56px;
  height: 46px;
  filter: var(--contour);
}
.ghosts {
  position: relative;
  flex: none;
  width: 56px;
  height: 46px;
}
/* Opaque grays multiplied onto the card, so overlaps stay flat; the white contour keeps figures apart. */
.stack {
  position: absolute;
  inset: 0 -2px;
  mix-blend-mode: multiply;
  mask: linear-gradient(#000 56%, transparent 96%);
  -webkit-mask: linear-gradient(#000 56%, transparent 96%);
}
.ghost {
  position: absolute;
  bottom: 1px;
  width: 36px;
  height: 34px;
  filter: brightness(0) invert(0.84) drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff) drop-shadow(0 -1px 0 #fff);
}
.ghost:nth-child(1) {
  left: 0;
}
.ghost:nth-child(2) {
  right: 0;
}
.ghost:nth-child(3) {
  left: 12px;
  bottom: -3px;
  filter: brightness(0) invert(0.7) drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff) drop-shadow(0 -1px 0 #fff);
}
/* On the lit card the figures turn to white light: multiplied gray would brown the orange. */
.on .stack {
  mix-blend-mode: normal;
}
.on .ghost {
  filter: brightness(0) invert(1);
  opacity: 0.42;
}
.on .ghost:nth-child(3) {
  filter: brightness(0) invert(1);
  opacity: 0.72;
}
.ask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font: 800 var(--fs-title)/1 var(--font-latin);
  color: var(--ink);
  text-shadow: 0 0 2px #fff, 0 0 6px #fff;
}
b {
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 4px;
  font: 800 var(--fs-strong)/1.1 var(--font);
  color: var(--ink);
}
.on b {
  color: inherit;
}
b i {
  flex: none;
  width: 4px;
  height: 11px;
}
small {
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.06em;
}
.mark {
  position: absolute;
  right: 0;
  top: 0;
  width: 20px;
  height: 18px;
  color: var(--ink);
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
