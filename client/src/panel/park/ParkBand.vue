<script setup lang="ts">
// The park's coral band, the top edge of its one sheet of paper: the four page keys on the left; on the right the
// page's timer, a tactile info key, and the host standing behind the sheet with its head over the band's top edge,
// as on the check-in calendar.
import { computed, ref } from "vue";
import { reducedMotion } from "../../stores/theme";
import { arrowSelect } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import type { BandEntry, ParkTab } from "./band";

const props = defineProps<{
  tabs: { id: ParkTab; label: string }[];
  modelValue: ParkTab;
  disabled?: boolean;
  host?: string;
  hostKind?: BandEntry["hostKind"];
  timer?: BandEntry["timer"];
  info?: BandEntry["info"];
}>();
const emit = defineEmits<{ "update:modelValue": [id: ParkTab] }>();

const list = ref<HTMLElement>();
/** Live event state (e.g. 比赛中 / 开奖中): timer has a label and no countdown digits. */
const isLive = computed(() => !!props.timer && !props.timer.time);
/** Final minute of a countdown (0:59 down to 0:00): heightened urgency without harshness. */
const isSoon = computed(() => !!props.timer?.time && /^0:\d\d$/.test(props.timer.time));

function onTabKey(e: KeyboardEvent) {
  if (props.disabled) return;
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    arrowSelect(e, list.value);
    return;
  }
  const items = list.value ? [...list.value.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")] : [];
  if (!items.length) return;
  if (e.key === "Home" || e.key === "End") {
    e.preventDefault();
    const btn = items[e.key === "Home" ? 0 : items.length - 1]!;
    btn.focus();
    btn.click();
    return;
  }
  if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing) {
    const n = Number(e.key);
    if (Number.isInteger(n) && n >= 1 && n <= items.length) {
      e.preventDefault();
      e.stopPropagation();
      const btn = items[n - 1]!;
      btn.focus();
      if (props.tabs[n - 1]) emit("update:modelValue", props.tabs[n - 1]!.id);
    }
  }
}
</script>

<template>
  <header class="park-band" :class="{ calm: reducedMotion }">
    <div ref="list" class="tabs" role="tablist" aria-label="乐园分页" @keydown="onTabKey">
      <button
        v-for="t in tabs" :key="t.id" type="button" role="tab" class="tab"
        :class="{ on: t.id === modelValue }" :aria-selected="t.id === modelValue"
        :tabindex="!disabled && t.id === modelValue ? 0 : -1" :disabled="disabled"
        @click="$emit('update:modelValue', t.id)"
      ><span>{{ t.label }}</span></button>
    </div>

    <p v-if="timer" class="timer" :class="{ live: isLive, soon: isSoon }" role="timer">
      <template v-if="timer.time">
        <small>{{ timer.label }}</small>
        <b>{{ timer.time }}</b>
      </template>
      <!-- No number (the race running, the draw under way): a live badge with a gentle coral pulse dot. -->
      <template v-else>
        <i class="live-dot" aria-hidden="true"></i>
        <strong>{{ timer.label }}</strong>
      </template>
    </p>
    <button
      v-if="info" type="button" class="info" :class="{ alone: !timer }"
      :title="info.label" :aria-label="info.label" @click="info.open"
    >
      <Icon name="info" :size="18" />
    </button>

    <span v-if="host" class="host-stage" :class="{ token: hostKind === 'token' }" aria-hidden="true">
      <!-- Reduced motion swaps the host in place: an out-in Transition with css off breaks on a quick swap. -->
      <img v-if="reducedMotion" class="host" :class="{ token: hostKind === 'token' }" :src="host" alt="" draggable="false" />
      <Transition v-else name="host" mode="out-in">
        <img :key="host" class="host" :class="{ token: hostKind === 'token' }" :src="host" alt="" draggable="false" />
      </Transition>
    </span>
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
  background: linear-gradient(180deg, color-mix(in oklab, var(--c-400) 86%, #fff), var(--c-400) 28%, var(--c-500));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.44),
    inset 0 -1px 0 rgba(var(--c-900-rgb), 0.08);
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
  opacity: 0.3;
  -webkit-mask:
    url("../../assets/patterns/halftone.svg") 0 -40px / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 40%, #000 76%);
  -webkit-mask-composite: source-in;
  mask:
    url("../../assets/patterns/halftone.svg") 0 -40px / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 40%, #000 76%);
  mask-composite: intersect;
}
.tabs,
.timer,
.info,
.host-stage {
  position: relative;
  z-index: 1;
}

/* ---- Two-layer rounded keycaps (as PoolTabs): ::before is the anchored lip plate, ::after is the lit face.
 * Across rest (0 + 3), hover (-1 + 4), latched (2 + 1) and active (3 + 0), --key-y + --key-lip-h stays 3px,
 * so pressing never moves the bottom edge or shifts the band. */
.tabs {
  display: flex;
  gap: 8px;
  min-width: 0;
  margin-bottom: 3px;
}
.tab {
  --face: linear-gradient(180deg, color-mix(in oklab, var(--c-500) 74%, #fff), var(--c-600));
  --face-inset: inset 0 1px 0 rgba(255, 255, 255, 0.36);
  --lip: var(--c-700);
  --key-lip-h: 3px;
  --key-y: 0px;
  --lip-shadow: 0 4px 8px -3px rgba(var(--c-900-rgb), 0.28);
  position: relative;
  isolation: isolate;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 64px;
  height: 36px;
  padding: 0 16px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-key);
  background: none;
  color: #fff;
  text-shadow: 0 1px 1px rgba(var(--c-900-rgb), 0.24);
  font: 800 var(--fs-number)/1 var(--font);
  white-space: nowrap;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transform: translateY(var(--key-y));
  transition:
    transform var(--dur-release) var(--ease-spring),
    color var(--dur-fast);
}
.tab::before,
.tab::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}
.tab::before {
  z-index: -2;
  background: var(--lip);
  box-shadow: var(--lip-shadow);
  transform: translateY(var(--key-lip-h));
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring),
    background var(--dur-fast);
}
.tab::after {
  z-index: -1;
  background: var(--face);
  box-shadow: var(--face-inset);
}
.tab:hover:not(:disabled):not(.on) {
  --face: linear-gradient(180deg, #fff, var(--key-white-shade));
  --face-inset: inset 0 1px 0 #fff;
  --lip: var(--c-200);
  --key-y: -1px;
  --key-lip-h: 4px;
  color: var(--ink);
  text-shadow: none;
}
.tab:active:not(:disabled):not(.on) {
  --key-y: 3px;
  --key-lip-h: 0px;
  --lip-shadow: 0 1px 2px -1px rgba(var(--c-900-rgb), 0.2);
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.tab:active:not(:disabled):not(.on)::before {
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
/* Latched: white keycap sitting partway down on a 1px lip sliver, coral type. */
.tab.on:not(:disabled) {
  --face: linear-gradient(180deg, #fff, var(--key-white-shade));
  --face-inset: inset 0 1px 0 #fff;
  --lip: var(--c-300);
  --key-y: 2px;
  --key-lip-h: 1px;
  --lip-shadow: 0 2px 5px -2px rgba(var(--c-900-rgb), 0.24);
  color: var(--c-700);
  text-shadow: none;
  cursor: default;
}
/* Locked, or no park on this server: flat tonal label with zero lip. */
.tab:disabled {
  --face: rgba(255, 255, 255, 0.16);
  --face-inset: none;
  --lip: transparent;
  --key-y: 0px;
  --key-lip-h: 0px;
  --lip-shadow: none;
  color: rgba(255, 255, 255, 0.72);
  text-shadow: none;
  cursor: default;
}
.tab:focus-visible {
  outline-offset: 3px;
}

/* ---- The page's timer capsule: recessed coral-plum well for countdowns, sunlit cream badge when live. */
.timer {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  margin: 0 0 0 auto;
  padding: 0 12px;
  box-sizing: border-box;
  border-radius: 999px;
  background: rgba(var(--c-900-rgb), 0.17);
  box-shadow:
    inset 0 1px 2px rgba(var(--c-900-rgb), 0.16),
    0 1px 0 rgba(255, 255, 255, 0.24);
  white-space: nowrap;
  transition: background var(--dur-base), box-shadow var(--dur-base);
}
.timer small {
  font: 700 var(--fs-label)/1 var(--font);
  color: rgba(255, 255, 255, 0.92);
}
.timer b {
  font: 800 26px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: #fff;
  text-shadow: 0 1px 2px rgba(var(--c-900-rgb), 0.24);
}
/* Final minute: deeper warm capsule with a calm breathing halo. */
.timer.soon {
  background: rgba(var(--c-900-rgb), 0.3);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.4),
    0 0 12px rgba(255, 255, 255, 0.2);
  animation: timer-soon 2.2s var(--ease-in-out) infinite;
}
/* Live event (比赛中 / 开奖中): crisp cream pill with a gently pulsing coral beacon. */
.timer.live {
  gap: 7px;
  padding: 0 13px 0 11px;
  background: linear-gradient(180deg, #fff, var(--c-50));
  box-shadow:
    inset 0 1px 0 #fff,
    0 2px 8px -2px rgba(var(--c-900-rgb), 0.24);
}
.live-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-600);
  box-shadow: 0 0 0 3px rgba(var(--c-500-rgb), 0.28);
  animation: live-pulse 2s var(--ease-in-out) infinite;
}
.timer strong {
  font: 800 var(--fs-strong)/1 var(--font);
  color: var(--c-700);
}
@keyframes timer-soon {
  50% {
    box-shadow:
      inset 0 0 0 1px rgba(255, 255, 255, 0.65),
      0 0 16px rgba(255, 255, 255, 0.34);
  }
}
@keyframes live-pulse {
  50% {
    transform: scale(1.18);
    box-shadow: 0 0 0 5px rgba(var(--c-500-rgb), 0.14);
  }
}

/* ---- Info key: tactile round-cornered keycap on the coral band. */
.info {
  --face: linear-gradient(180deg, color-mix(in oklab, var(--c-500) 74%, #fff), var(--c-600));
  --lip: var(--c-700);
  --key-lip-h: 2px;
  --key-y: 0px;
  position: relative;
  isolation: isolate;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-bottom: 2px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-key-s);
  background: none;
  color: #fff;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transform: translateY(var(--key-y));
  transition: transform var(--dur-release) var(--ease-spring), color var(--dur-fast);
}
.info.alone {
  margin-left: auto;
}
.info::before,
.info::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}
.info::before {
  z-index: -2;
  background: var(--lip);
  box-shadow: 0 3px 6px -2px rgba(var(--c-900-rgb), 0.26);
  transform: translateY(var(--key-lip-h));
  transition: transform var(--dur-release) var(--ease-spring), background var(--dur-fast);
}
.info::after {
  z-index: -1;
  background: var(--face);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.36);
}
.info:hover {
  --face: linear-gradient(180deg, #fff, var(--key-white-shade));
  --lip: var(--c-200);
  --key-y: -1px;
  --key-lip-h: 3px;
  color: var(--c-700);
}
.info:active {
  --key-y: 2px;
  --key-lip-h: 0px;
  transition-duration: var(--dur-press);
}
.info:active::before {
  transition-duration: var(--dur-press);
}

/* ---- The host: cut off at the waist by the sheet, its head over the band's top edge, breathing gently at rest. */
.host-stage {
  position: absolute;
  right: 14px;
  bottom: -40px;
  width: var(--host-h);
  height: var(--host-h);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  pointer-events: none;
  animation: host-breathe 4.4s var(--ease-in-out) infinite;
}
/* Warm sunlit halo behind the shopkeeper so the sticker pops against the halftone awning. */
.host-stage::before {
  content: "";
  position: absolute;
  inset: 14% 10% 24%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.36) 0%, transparent 72%);
  pointer-events: none;
}
.host-stage.token {
  --token-h: 84px;
  right: 30px;
  bottom: -6px;
  width: var(--token-h);
  height: var(--token-h);
}
.host {
  height: 100%;
  max-width: 100%;
  object-fit: contain;
  object-position: 50% 100%;
  rotate: 6deg;
  filter: var(--sticker-lg);
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
@keyframes host-breathe {
  50% {
    transform: translateY(-2.5px);
  }
}

.calm .tab,
.calm .tab::before,
.calm .info,
.calm .info::before {
  transition: none;
}
.calm .timer.soon,
.calm .live-dot,
.calm .host-stage {
  animation: none;
}

@container panel (max-width: 920px) {
  .park-band {
    --host-room: 136px;
    gap: 9px;
    padding-left: 16px;
  }
  .tabs {
    gap: 6px;
  }
  .tab {
    min-width: 58px;
    padding: 0 13px;
  }
  .timer {
    padding: 0 10px;
    gap: 6px;
  }
  .timer b {
    font-size: 24px;
  }
}

@container panel (max-width: 760px) {
  .park-band {
    --host-h: 108px;
    --host-room: 118px;
    gap: 8px;
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
  .host-stage {
    display: none;
  }
  .tab {
    height: 32px;
    padding: 0 10px;
    font-size: var(--fs-strong);
  }
  .timer {
    height: 30px;
    gap: 6px;
    padding: 0 9px;
  }
  .timer b {
    font-size: 22px;
  }
  .info {
    width: 30px;
    height: 30px;
  }
}
</style>
