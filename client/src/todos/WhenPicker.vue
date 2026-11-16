<script setup lang="ts">
// The time picker of the todos' window, for a new todo and for one in the list: a week of days and a month to page
// through, a switch for a time of day (off: the whole day), quick hours and the hour and minute boxes. With `repeat`
// it also holds the repeat choice. A choice takes effect at once.
import { computed, nextTick, ref } from "vue";
import {
  REPEATS, REPEAT_LABEL, dayStart, dayStrip, hourOn, monthWeeks, quickHours, timeAt, type TodoRepeat, type TodoWhen,
} from "../todo";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ modelValue: TodoWhen; now: number; repeat?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [when: TodoWhen] }>();

const when = computed(() => props.modelValue);
const set = (patch: Partial<TodoWhen>) => emit("update:modelValue", { ...when.value, ...patch });
const today = computed(() => dayStart(props.now));
/** The chosen day's midnight, null without one. */
const day = computed(() => (when.value.at == null ? null : dayStart(when.value.at)));
const timed = computed(() => when.value.at != null && !when.value.allDay);

// ---- the day
const strip = computed(() => dayStrip(props.now));
/** Chosen past the strip's week: the month key shows the date and stands chosen. */
const farDay = computed(() => (day.value != null && !strip.value.some((d) => d.at === day.value) ? new Date(day.value) : null));
function pickDay(midnight: number) {
  if (!timed.value) return set({ at: midnight, allDay: true });
  const d = new Date(when.value.at!);
  set({ at: timeAt(midnight, 0, d.getHours(), d.getMinutes()), allDay: false });
}

const month = ref<number | null>(null);
const weeks = computed(() => (month.value == null ? [] : monthWeeks(month.value)));
const monthTitle = computed(() => {
  if (month.value == null) return "";
  const d = new Date(month.value);
  return `${d.getFullYear()}年${d.getMonth() + 1}月`;
});
/** The month shown can go back to the current one, no further. */
const canPrev = computed(() => month.value != null && dayStart(new Date(month.value).setDate(1)) > today.value);
function openMonth() {
  month.value = month.value == null ? (day.value ?? props.now) : null;
}
function turn(by: number) {
  const d = new Date(month.value!);
  d.setDate(1);
  d.setMonth(d.getMonth() + by);
  month.value = d.getTime();
}
function pickMonthDay(midnight: number) {
  pickDay(midnight);
  month.value = null;
}

// ---- the time of day
const TIME_FIRST_HOUR = 9;
/** The switch on: today's next full hour (the last minute of the day once none is left), another day's nine. */
function timeOn(on: boolean) {
  const base = day.value ?? today.value;
  if (!on) return set({ at: base, allDay: true });
  let at = timeAt(base, 0, TIME_FIRST_HOUR, 0);
  if (base === today.value) {
    const h = new Date(props.now).getHours() + 1;
    at = h > 23 ? timeAt(base, 0, 23, 59) : timeAt(base, 0, h, 0);
  }
  set({ at, allDay: false });
}
const hours = computed(() => (day.value == null ? [] : quickHours(day.value, props.now)));
const inAnHour = computed(() => (day.value === today.value ? hourOn(props.now) : null));
const clock = (h: number) => `${String(h).padStart(2, "0")}:00`;

type Part = "hour" | "minute";
const MIN_STEP = 5;
const two = (n: number) => String(n).padStart(2, "0");
const hh = computed(() => (timed.value ? two(new Date(when.value.at!).getHours()) : ""));
const mm = computed(() => (timed.value ? two(new Date(when.value.at!).getMinutes()) : ""));
function setPart(part: Part, value: number) {
  if (!timed.value) return;
  const d = new Date(when.value.at!);
  if (part === "hour") d.setHours(((value % 24) + 24) % 24);
  else d.setMinutes(((value % 60) + 60) % 60);
  set({ at: d.getTime() });
}
/** Hours go round the day; minutes go by five round the hour. */
function step(part: Part, by: number) {
  if (!timed.value) return;
  const d = new Date(when.value.at!);
  if (part === "hour") return setPart("hour", d.getHours() + by);
  const m = d.getMinutes();
  setPart("minute", by > 0 ? Math.floor(m / MIN_STEP) * MIN_STEP + MIN_STEP : Math.ceil(m / MIN_STEP) * MIN_STEP - MIN_STEP);
}
/** A number typed in: kept within its range; anything else shows the time as it was. */
function commit(part: Part, e: Event) {
  const input = e.target as HTMLInputElement;
  const n = Number.parseInt(input.value, 10);
  if (Number.isFinite(n)) setPart(part, Math.min(part === "hour" ? 23 : 59, Math.max(0, n)));
  void nextTick(() => { input.value = part === "hour" ? hh.value : mm.value; });
}
function onNumInput(e: Event) {
  const input = e.target as HTMLInputElement;
  const digits = input.value.replace(/\D/g, "").slice(0, 2);
  if (digits !== input.value) input.value = digits;
}
function onNumKey(part: Part, e: KeyboardEvent) {
  if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    step(part, e.key === "ArrowUp" ? 1 : -1);
  } else if (e.key === "Enter") {
    commit(part, e);
  }
}
// A wheel notch is one step; a touchpad's many small deltas add up to one.
const WHEEL_STEP = 50;
let wheel = 0;
function onWheel(part: Part, e: WheelEvent) {
  wheel += e.deltaY;
  while (Math.abs(wheel) >= WHEEL_STEP) {
    const by = wheel < 0 ? 1 : -1;
    step(part, by);
    wheel += by * WHEEL_STEP;
  }
}

/** A repeat without a day starts today. */
function pickRepeat(r: TodoRepeat) {
  if (when.value.at == null && r !== "none") set({ at: today.value, allDay: true, repeat: r });
  else set({ repeat: r });
}
const WEEK_HEAD = ["一", "二", "三", "四", "五", "六", "日"];
</script>

<template>
  <div class="when-picker" role="dialog" aria-label="时间">
    <template v-if="month == null">
      <div class="days" role="radiogroup" aria-label="日期">
        <button
          v-for="d in strip" :key="d.off" type="button" class="day" role="radio" :aria-checked="day === d.at"
          @click="pickDay(d.at)"
        >
          <small>{{ d.label }}</small><b>{{ d.date }}</b>
        </button>
        <button
          type="button" class="day more" :aria-checked="!!farDay" role="radio" title="日历" aria-label="日历"
          @click="openMonth"
        >
          <template v-if="farDay"><small>{{ farDay.getMonth() + 1 }}月</small><b>{{ farDay.getDate() }}</b></template>
          <Icon v-else name="calendar" :size="16" />
        </button>
      </div>

      <div class="time-row">
        <Icon name="clock" :size="15" />
        <span>时间</span>
        <span v-if="timed" class="clock">
          <input
            class="num" type="text" inputmode="numeric" maxlength="2" aria-label="时" :value="hh"
            @input="onNumInput" @change="commit('hour', $event)" @keydown="onNumKey('hour', $event)"
            @wheel.prevent="onWheel('hour', $event)" @focus="($event.target as HTMLInputElement).select()"
          />
          <i aria-hidden="true">:</i>
          <input
            class="num" type="text" inputmode="numeric" maxlength="2" aria-label="分" :value="mm"
            @input="onNumInput" @change="commit('minute', $event)" @keydown="onNumKey('minute', $event)"
            @wheel.prevent="onWheel('minute', $event)" @focus="($event.target as HTMLInputElement).select()"
          />
        </span>
        <input
          class="ui-switch" type="checkbox" aria-label="时间" :checked="timed"
          @change="timeOn(($event.target as HTMLInputElement).checked)"
        />
      </div>
      <div v-if="timed" class="hours">
        <button
          v-for="q in hours" :key="q.hour" type="button" class="hour" :disabled="q.past" :aria-pressed="when.at === q.at"
          @click="set({ at: q.at, allDay: false })"
        >
          {{ clock(q.hour) }}
        </button>
        <button
          v-if="inAnHour != null" type="button" class="hour soon" :aria-pressed="when.at === inAnHour"
          @click="set({ at: inAnHour, allDay: false })"
        >
          一小时后
        </button>
      </div>

      <div v-if="repeat" class="seg" role="radiogroup" aria-label="重复">
        <button
          v-for="r in REPEATS" :key="r" type="button" role="radio" :aria-checked="when.repeat === r" @click="pickRepeat(r)"
        >
          {{ REPEAT_LABEL[r] }}
        </button>
      </div>
    </template>

    <div v-else class="month">
      <div class="month-head">
        <button type="button" class="turn" :disabled="!canPrev" aria-label="上个月" @click="turn(-1)">
          <Icon name="back" :size="14" />
        </button>
        <b>{{ monthTitle }}</b>
        <button type="button" class="turn" aria-label="下个月" @click="turn(1)">
          <Icon name="forward" :size="14" />
        </button>
      </div>
      <div class="grid" role="grid">
        <span v-for="w in WEEK_HEAD" :key="w" class="head" aria-hidden="true">{{ w }}</span>
        <template v-for="(week, i) in weeks" :key="i">
          <span v-for="(cell, j) in week" :key="j" class="cell-wrap">
            <button
              v-if="cell != null" type="button" class="cell" :class="{ today: cell === today }"
              :disabled="cell < today" :aria-pressed="cell === day" @click="pickMonthDay(cell)"
            >
              {{ new Date(cell).getDate() }}
            </button>
          </span>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* A paper sheet over the window: the days, the time of day and, for a todo of the list, the repeat. */
.when-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.1), 0 10px 28px -8px rgba(var(--shadow-rgb), 0.32);
  color: var(--ink);
}

/* The week: seven days and the month key, the chosen one lifted off the tint. */
.days {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
  padding: 3px;
  border-radius: 11px;
  background: var(--c-50);
}
.day {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink-2);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.day small {
  font: 700 10px/1 var(--font);
  color: var(--ink-3);
  white-space: nowrap;
}
.day b {
  font: 800 15px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}
.day:hover {
  background: var(--surface);
}
.day[aria-checked="true"] {
  background: var(--surface);
  color: var(--c-600);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12);
}
.day[aria-checked="true"] small {
  color: var(--c-600);
}
.day.more {
  color: var(--ink-3);
}

/* The time of day: its switch on the right, the hour and minute boxes before it while on. */
.time-row {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 2px 0 6px;
  color: var(--ink-3);
}
.time-row > span:first-of-type {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.time-row .ui-switch {
  margin-left: auto;
}
.clock {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
}
.clock + .ui-switch {
  margin-left: 6px;
}
.clock i {
  font: 800 14px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.num {
  width: 32px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  outline: none;
  background: var(--c-50);
  color: var(--ink);
  text-align: center;
  font: 800 16px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  user-select: text;
  -webkit-user-select: text;
  transition: box-shadow var(--dur-fast);
}
.num:focus {
  box-shadow: inset 0 0 0 1.5px var(--c-500);
}

/* Quick hours: flat tiles; the passed ones of today fade. */
.hours {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.hour {
  flex: auto;
  height: 26px;
  padding: 0 6px;
  border: 0;
  border-radius: 8px;
  background: var(--c-50);
  color: var(--ink-2);
  font: 800 13px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast), opacity var(--dur-fast);
}
.hour.soon {
  font: 700 var(--fs-label)/1 var(--font);
}
.hour:hover:not(:disabled) {
  background: var(--c-100);
  color: var(--ink);
}
.hour[aria-pressed="true"] {
  background: var(--c-100);
  color: var(--c-700);
  box-shadow: inset 0 0 0 1.5px var(--c-500);
}
.hour:disabled {
  opacity: 0.4;
  cursor: default;
}

/* The repeat choice: a small segmented control. */
.seg {
  display: flex;
  padding: 2px;
  border-radius: 9px;
  background: var(--c-100);
}
.seg button {
  flex: auto;
  height: 26px;
  padding: 0 4px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--ink-3);
  font: 700 var(--fs-label)/1 var(--font);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.seg button:hover {
  color: var(--ink);
}
.seg button[aria-checked="true"] {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.15);
}

/* The month: a title between two page keys, then the weeks from Monday. */
.month-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 28px;
  padding: 0 2px;
}
.month-head b {
  font: 800 var(--fs-body)/1 var(--font);
}
.turn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink-2);
  cursor: pointer;
}
.turn:hover:not(:disabled) {
  background: var(--c-50);
}
.turn:disabled {
  opacity: 0.3;
  cursor: default;
}
.grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}
.grid .head {
  text-align: center;
  font: 700 10px/20px var(--font);
  color: var(--ink-3);
}
.cell-wrap {
  display: grid;
  place-items: center;
}
.cell {
  width: 32px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  font: 800 14px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.cell:hover:not(:disabled) {
  background: var(--c-50);
}
.cell.today {
  color: var(--c-600);
}
.cell[aria-pressed="true"] {
  background: var(--c-500);
  color: var(--surface);
}
.cell:disabled {
  color: var(--ink-3);
  opacity: 0.4;
  cursor: default;
}
</style>
