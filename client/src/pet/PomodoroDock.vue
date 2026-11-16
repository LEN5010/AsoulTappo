<script setup lang="ts">
// The tomato timer's page of the quick emotes plate (src/stores/pomodoro.ts): the lengths and a start key, or while it
// runs a ring with the time left and a stop key; under either, switches for the tune, the system notice, going on by
// itself and the long rest. Hung under the strip or the own name plate like the status keys; where the screen ends below it,
// it opens upwards above `ceiling`. The settings are the same as on the settings page.
import { computed, onMounted, ref } from "vue";
import { LONG_EVERY, clockText } from "../pomodoro";
import { pomodoroTune, wakeAudio } from "../audio/sfx";
import { beginPomodoro, endPomodoro, pomodoro, pomodoroLeft, pomodoroProgress } from "../stores/pomodoro";
import { settings } from "../stores/settings";
import Icon from "../ui/Icon.vue";
import { useLift } from "./lift";

const props = defineProps<{ ceiling?: number }>();
const emit = defineEmits<{ done: [] }>();

const root = ref<HTMLElement>();
const { up, style: lift } = useLift(root, () => props.ceiling);
// Wider than the strip it hangs from: next to a screen edge it moves sideways to stay on screen.
const EDGE = 4;
const shift = ref(0);
onMounted(() => {
  const r = root.value?.getBoundingClientRect();
  if (!r) return;
  if (r.right > window.innerWidth - EDGE) shift.value = Math.round(window.innerWidth - EDGE - r.right);
  else if (r.left < EDGE) shift.value = Math.round(EDGE - r.left);
});

interface Dial { key: "pomodoroFocus" | "pomodoroRest"; label: string; min: number; max: number; step: number }
const DIALS: Dial[] = [
  { key: "pomodoroFocus", label: "专注", min: 5, max: 120, step: 5 },
  { key: "pomodoroRest", label: "休息", min: 1, max: 60, step: 1 },
];
function turn(d: Dial, by: number) {
  settings[d.key] = Math.min(d.max, Math.max(d.min, settings[d.key] + by * d.step));
}
// A wheel notch is one step; a touchpad's many small deltas add up to one.
const WHEEL_STEP = 50;
let wheel = 0;
function onWheel(d: Dial, e: WheelEvent) {
  wheel += e.deltaY;
  while (Math.abs(wheel) >= WHEEL_STEP) {
    const by = wheel < 0 ? 1 : -1;
    turn(d, by);
    wheel += by * WHEEL_STEP;
  }
}

type Switch = "pomodoroSound" | "pomodoroNotify" | "pomodoroAuto" | "pomodoroLong";
const SWITCHES: { key: Switch; icon: string; label: string; title?: string }[] = [
  { key: "pomodoroSound", icon: "sound", label: "提示音" },
  { key: "pomodoroNotify", icon: "bell", label: "系统通知" },
  { key: "pomodoroAuto", icon: "refresh", label: "自动下一轮" },
  { key: "pomodoroLong", icon: "cup", label: "长休息", title: `每 ${LONG_EVERY} 轮休息久一点` },
];
function flip(key: Switch) {
  settings[key] = !settings[key];
  // Turning the tune on plays it once, so it is heard before it is needed.
  if (key === "pomodoroSound" && settings[key]) {
    wakeAudio();
    pomodoroTune("rest");
  }
}

const phase = computed(() => {
  const p = pomodoro.value;
  if (!p) return "";
  return p.phase === "focus" ? `专注 · 第 ${p.round} 轮` : p.long ? "长休息" : "休息";
});
/** The ring around the icon fills as the phase goes. */
const RING_R = 19;
const RING = 2 * Math.PI * RING_R;
const ringGap = computed(() => RING * (1 - pomodoroProgress.value));

function start() {
  // The start key is a press in this window: the tunes can play when the phase ends.
  wakeAudio();
  beginPomodoro();
  emit("done");
}
function stop() {
  endPomodoro();
  emit("done");
}
</script>

<template>
  <div
    ref="root" class="pomo-dock" :class="{ up }" :style="[lift, { '--shift': `${shift}px` }]"
    role="group" aria-label="番茄钟" data-hit data-no-drag
  >
    <div v-if="!pomodoro" class="top">
      <div v-for="d in DIALS" :key="d.key" class="dial" @wheel.prevent="onWheel(d, $event)">
        <small>{{ d.label }}</small>
        <div class="set">
          <button
            type="button" class="step" :aria-label="`${d.label}少一点`" :disabled="settings[d.key] <= d.min"
            @click="turn(d, -1)"
          >
            <Icon name="minus" :size="12" />
          </button>
          <b>{{ settings[d.key] }}<span>分钟</span></b>
          <button
            type="button" class="step" :aria-label="`${d.label}多一点`" :disabled="settings[d.key] >= d.max"
            @click="turn(d, 1)"
          >
            <Icon name="plus" :size="12" />
          </button>
        </div>
      </div>
      <button type="button" class="go ui-btn primary" @click="start">
        <Icon name="tomato" :size="18" /><span>开始</span>
      </button>
    </div>
    <div v-else class="top">
      <span class="ring" :class="pomodoro.phase" aria-hidden="true">
        <svg class="arc-box" viewBox="0 0 44 44" width="44" height="44">
          <circle class="track" cx="22" cy="22" :r="RING_R" />
          <circle class="arc" cx="22" cy="22" :r="RING_R" :stroke-dasharray="RING" :stroke-dashoffset="ringGap" />
        </svg>
        <Icon :name="pomodoro.phase === 'focus' ? 'tomato' : 'cup'" :size="18" />
      </span>
      <span class="now">
        <small>{{ phase }}</small>
        <b>{{ clockText(pomodoroLeft) }}</b>
      </span>
      <button type="button" class="go ui-btn" @click="stop">结束</button>
    </div>
    <div class="opts">
      <button
        v-for="s in SWITCHES" :key="s.key" type="button" class="opt" :aria-pressed="settings[s.key]" :title="s.title"
        @click="flip(s.key)"
      >
        <Icon :name="s.icon" :size="14" />
        <span>{{ s.label }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* The paper plate of the quick emotes: the timer on top, its switches in a row underneath. */
.pomo-dock {
  position: absolute;
  left: 50%;
  top: calc(100% + 10px);
  transform: translateX(calc(-50% + var(--shift, 0px)));
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  box-sizing: border-box;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 8px 20px -6px rgba(var(--shadow-rgb), 0.35);
  font-family: var(--font);
  color: var(--ink);
  white-space: nowrap;
  animation: drop-in var(--dur-base) var(--ease-out);
  cursor: default;
}
.pomo-dock.up {
  top: auto;
  bottom: calc(100% + 10px);
  animation-name: rise-in;
}
.top {
  display: flex;
  align-items: center;
  gap: 6px;
  /* Room for the keys' lip. */
  padding-bottom: 3px;
}

/* A length sits in a tinted well: its name over the number, a round key on each side. */
.dial {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 5px 4px 4px;
  border-radius: 12px;
  background: var(--c-50);
}
.dial small {
  font: 700 11px/1 var(--font);
  color: var(--ink-3);
}
.set {
  display: flex;
  align-items: center;
  gap: 2px;
}
.set b {
  min-width: 40px;
  text-align: center;
  font: 800 20px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}
.set b span {
  margin-left: 1px;
  font: 700 11px/1 var(--font);
  color: var(--ink-2);
}
.step {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ink-2);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.step:hover:not(:disabled) {
  background: var(--surface);
  color: var(--ink);
}
.step:active:not(:disabled) {
  background: var(--c-100);
}
.step:disabled {
  opacity: 0.3;
  cursor: default;
}
.go {
  flex: none;
  height: 48px;
  min-width: 74px;
  padding: 0 14px;
  border-radius: 12px;
}
.go .icon {
  margin-left: -2px;
}

/* While it runs: a ring that fills with the phase, the phase over the time left. */
.ring {
  position: relative;
  flex: none;
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  color: var(--c-600);
}
.ring .arc-box {
  position: absolute;
  inset: 2px;
  rotate: -90deg;
}
.ring circle {
  fill: none;
  stroke-width: 4;
}
.ring .track {
  stroke: var(--c-100);
}
.ring .arc {
  stroke: var(--c-500);
  stroke-linecap: round;
  transition: stroke-dashoffset 1s linear;
}
.ring.rest .arc {
  stroke: var(--c-300);
}
.now {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-left: 4px;
}
.now small {
  font: 700 11px/1 var(--font);
  color: var(--ink-3);
}
.now b {
  font: 800 26px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}

/* The switches: flat tiles on the paper, tinted coral while on (the status keys' look). */
.opts {
  display: flex;
  gap: 4px;
  padding-top: 7px;
  border-top: 1px solid var(--c-100);
}
.opt {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--ink-3);
  font: 700 var(--fs-label)/1 var(--font);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.opt:hover {
  background: var(--c-50);
  color: var(--ink-2);
}
.opt[aria-pressed="true"] {
  background: var(--c-100);
  color: var(--ink);
}
.opt[aria-pressed="true"] .icon {
  color: var(--c-600);
}
@keyframes drop-in {
  from {
    opacity: 0;
    transform: translate(calc(-50% + var(--shift, 0px)), -8px);
  }
}
@keyframes rise-in {
  from {
    opacity: 0;
    transform: translate(calc(-50% + var(--shift, 0px)), 8px);
  }
}
</style>
