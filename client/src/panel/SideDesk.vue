<script setup lang="ts">
// The pet on the desk right now, standing out of a card in the sidebar with today's taps.
// Pressing it opens the backpack, where the pet is chosen.
import { computed } from "vue";
import { getCharacter, skinSeries } from "../characters";
import { characterColor, memberOf } from "../manifest";
import { counter } from "../stores/counter";
import { settings } from "../stores/settings";
import { ui } from "../stores/ui";
import PetBust from "./PetBust.vue";

const member = computed(() => memberOf(settings.character));
const series = computed(() => skinSeries(settings.character) || "原皮");
const bg = computed(() => getCharacter(settings.character)?.bg ?? "");
</script>

<template>
  <button
    type="button" class="desk" :class="{ on: ui.page === 'emotes' }" :style="{ '--member': characterColor(member) }"
    :aria-label="`桌宠${settings.character}，今日敲击 ${counter.today} 次`" @click="ui.page = 'emotes'"
  >
    <PetBust v-if="bg" class="bust" :src="bg" />
    <span class="name"><b><i></i>{{ member }}</b><small>{{ series }}</small></span>
    <span class="taps"><b>{{ counter.today }}</b><small>今日敲击</small></span>
  </button>
</template>

<style scoped>
.desk {
  position: relative;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-items: end;
  column-gap: 6px;
  padding: 0 12px 10px 4px;
  border: 0;
  border-radius: var(--radius-m);
  background: linear-gradient(180deg, var(--surface) 55%, color-mix(in oklab, var(--member) 12%, var(--surface)));
  box-shadow: inset 0 -3px 0 var(--member), 0 10px 20px -12px rgba(var(--ink-rgb), 0.45);
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.desk:hover {
  transform: translateY(-3px);
  box-shadow: inset 0 -3px 0 var(--member), 0 0 18px rgba(255, 255, 255, 0.75), 0 12px 22px -12px rgba(var(--ink-rgb), 0.5);
}
.desk:focus-visible {
  outline: 2px solid var(--ink);
  outline-offset: 3px;
}
/* The bust stands out of the card's top edge. */
.bust {
  grid-row: 1;
  width: 62px;
  height: 66px;
  margin: -24px 0 0 -2px;
  filter: var(--contour) drop-shadow(0 2px 3px rgba(var(--ink-rgb), 0.22));
  transition: transform var(--dur-slow) var(--ease-spring);
  transform-origin: 50% 100%;
}
.desk:hover .bust {
  transform: scale(1.08) rotate(-3deg);
}
.name {
  grid-row: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding-bottom: 4px;
}
.name b {
  display: flex;
  align-items: center;
  gap: 5px;
  font: 800 var(--fs-strong)/1.2 var(--font);
}
.name i {
  flex: none;
  width: 4px;
  height: 12px;
  background: var(--member);
}
.name small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.taps {
  grid-column: 1 / -1;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  margin: 2px 0 0 8px;
  padding-top: 7px;
  border-top: 1.5px dashed var(--line-2);
}
.taps b {
  font: 800 26px/1 var(--font-latin);
  color: var(--accent-deep);
}
.taps small {
  font-size: var(--fs-caption);
  font-weight: 800;
  color: var(--ink-2);
}
</style>
