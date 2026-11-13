<script setup lang="ts">
// The park's coral band, the top edge of its one sheet of paper: the four page keys on the left; on the right the
// page's timer, a quiet info key, and the host standing behind the sheet with its head over the band's top edge,
// as on the check-in calendar.
import { ref } from "vue";
import { reducedMotion } from "../../stores/theme";
import { arrowSelect } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import type { BandEntry, ParkTab } from "./band";

defineProps<{
  tabs: { id: ParkTab; label: string }[];
  modelValue: ParkTab;
  disabled?: boolean;
  host?: string;
  hostKind?: BandEntry["hostKind"];
  timer?: BandEntry["timer"];
  info?: BandEntry["info"];
}>();
defineEmits<{ "update:modelValue": [id: ParkTab] }>();

const list = ref<HTMLElement>();
</script>

<template>
  <header class="park-band" :class="{ calm: reducedMotion }">
    <div ref="list" class="tabs" role="tablist" aria-label="乐园分页" @keydown="arrowSelect($event, list)">
      <button
        v-for="t in tabs" :key="t.id" type="button" role="tab" class="ui-btn tab"
        :class="{ on: t.id === modelValue }" :aria-selected="t.id === modelValue" :disabled="disabled"
        @click="$emit('update:modelValue', t.id)"
      >{{ t.label }}</button>
    </div>

    <p v-if="timer" class="timer" role="timer">
      <template v-if="timer.time">
        <small>{{ timer.label }}</small>
        <b>{{ timer.time }}</b>
      </template>
      <!-- No number (the race running, the draw under way): the label alone, at reading size. -->
      <strong v-else>{{ timer.label }}</strong>
    </p>
    <button
      v-if="info" type="button" class="ui-btn ghost small info" :class="{ alone: !timer }"
      :title="info.label" :aria-label="info.label" @click="info.open"
    >
      <Icon name="info" :size="18" />
    </button>

    <!-- Reduced motion swaps the host in place: an out-in Transition with css off breaks on a quick swap. -->
    <img v-if="reducedMotion && host" class="host" :class="{ token: hostKind === 'token' }" :src="host" alt="" draggable="false" />
    <Transition v-else name="host" mode="out-in">
      <img v-if="host" :key="host" class="host" :class="{ token: hostKind === 'token' }" :src="host" alt="" draggable="false" />
    </Transition>
  </header>
</template>

<style scoped>
.park-band {
  --host-h: 128px;
  --host-room: 150px;
  --focus: #fff;
  position: relative;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 76px;
  padding: 0 var(--host-room) 0 20px;
  box-sizing: border-box;
  border-radius: var(--radius-l) var(--radius-l) 0 0;
  background: var(--grad-sky);
  user-select: none;
}
/* Printed into the coral, faint and behind the keys: halftone dots on the right half only. */
.park-band::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  pointer-events: none;
  opacity: 0.32;
  mask:
    url("../../assets/patterns/halftone.svg") 0 -40px / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 40%, #000 76%);
  mask-composite: intersect;
}
.tabs,
.timer,
.info,
.host {
  position: relative;
  z-index: 1;
}

/* ---- the page keys: white keycaps on the coral; the page shown is latched */
.tabs {
  display: flex;
  gap: 8px;
  min-width: 0;
  padding-bottom: 3px;
}
.tab {
  min-width: 64px;
  padding: 0 16px;
  font-size: var(--fs-strong);
}
.tab:focus-visible {
  outline-offset: 3px;
}
.tab.on:not(:disabled) {
  cursor: default;
}

/* ---- the page's timer: a white number with a small ink label */
.timer {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0 0 0 auto;
  white-space: nowrap;
}
.timer small {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink);
}
.timer b {
  font: 800 28px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: #fff;
}
.timer strong {
  font: 800 var(--fs-section)/1 var(--font);
  color: var(--ink);
}
.info {
  width: 32px;
  padding: 0;
  color: var(--ink);
}
.info.alone {
  margin-left: auto;
}

/* ---- the host: cut off at the waist by the sheet, its head over the band's top edge */
.host {
  position: absolute;
  right: 14px;
  bottom: -40px;
  height: var(--host-h);
  max-width: var(--host-h);
  object-fit: contain;
  object-position: 50% 100%;
  rotate: 6deg;
  filter: var(--sticker-lg);
  pointer-events: none;
}
/* A tuanzi is all head: it stands on the sheet's edge with only its chin behind it. */
.host.token {
  --token-h: 84px;
  right: 30px;
  bottom: -6px;
  height: var(--token-h);
  max-width: var(--token-h);
}
/* A new host: the old one sinks behind the sheet and the new one comes up. */
.host-enter-active {
  transition: translate 420ms var(--ease-pop), rotate 420ms var(--ease-pop);
}
.host-leave-active {
  transition: translate 150ms var(--ease-in);
}
.host-enter-from,
.host-leave-to {
  translate: 0 72%;
}
.host-enter-from {
  rotate: -6deg;
}

@container panel (max-width: 760px) {
  .park-band {
    --host-h: 108px;
    --host-room: 120px;
    gap: 10px;
    padding-left: 14px;
  }
  .tabs {
    gap: 6px;
  }
  .tab {
    min-width: 0;
    padding: 0 11px;
  }
}
/* Short or narrow panels: a low band without the host; the timer comes down to the keys' size. */
@container panel (max-height: 560px) or (max-width: 680px) {
  .park-band {
    height: 52px;
    padding-right: 12px;
  }
  .host {
    display: none;
  }
  .tab {
    height: 32px;
    padding: 0 10px;
    font-size: var(--fs-body);
  }
  .timer {
    gap: 6px;
  }
  .timer b {
    font-size: 24px;
  }
}
</style>
