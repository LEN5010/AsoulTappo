<script setup lang="ts">
// The todos' page of the quick emotes plate (src/stores/todo.ts): one list, open todos by time and the ticked-off ones
// folded under it; the last line adds a todo, and while it is being written a bar of quick times and a custom date
// and time come up under it. The tune and the system notice switch in the top corner. Hung under the strip or the own
// name plate like the tomato timer's page; where the screen ends below it, it opens upwards above `ceiling`.
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
  REPEATS, REPEAT_LABEL, TITLE_MAX, cleanTitle, dayOffset, dayStrip, doneTodos, isOverdue, quickTimes, sortTodos, timeAt,
  whenText, type Todo, type TodoRepeat,
} from "../todo";
import { pomodoroTune, wakeAudio } from "../audio/sfx";
import { setOverlayTyping } from "../composables/tauri";
import { addTodo, finishTodo, removeTodo, todoNow, todos, undoTodo } from "../stores/todo";
import { settings } from "../stores/settings";
import Icon from "../ui/Icon.vue";
import { useLift } from "./lift";

const props = defineProps<{ ceiling?: number }>();
const emit = defineEmits<{ done: [] }>();

const root = ref<HTMLElement>();
const box = ref<HTMLInputElement>();
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

// ---- the list
const open = computed(() => sortTodos(todos.value.filter((t) => t.doneAt == null)));
const done = computed(() => doneTodos(todos.value));
const doneShown = ref(false);
const scroller = ref<HTMLElement>();
/** Unfolded, the ticked-off group scrolls up to the top of the list, so its todos show; folded, the list goes back up. */
async function toggleDone(e: MouseEvent) {
  doneShown.value = !doneShown.value;
  const fold = e.currentTarget as HTMLElement;
  await nextTick();
  const list = scroller.value;
  if (list) list.scrollTo({ top: doneShown.value ? fold.offsetTop - list.offsetTop : 0, behavior: "smooth" });
}
const late = (t: Todo) => isOverdue(t, todoNow.value);
/** Which edges of the list have rows cut off past them: those edges fade out. */
const cut = reactive({ top: false, bottom: false });
function measure() {
  const el = scroller.value;
  if (!el) return;
  cut.top = el.scrollTop > 1;
  cut.bottom = el.scrollTop + el.clientHeight < el.scrollHeight - 1;
}
onMounted(measure);

/** A tick stays a moment before the todo goes to the ticked-off ones; a second press in that time takes it back. */
const SETTLE_MS = 1000;
const settling = reactive(new Set<string>());
const timers = new Map<string, ReturnType<typeof setTimeout>>();
function settle(id: string) {
  timers.delete(id);
  settling.delete(id);
  finishTodo(id);
}
function tick(t: Todo) {
  if (t.doneAt != null) return undoTodo(t.id);
  const timer = timers.get(t.id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(t.id);
    settling.delete(t.id);
    return;
  }
  settling.add(t.id);
  timers.set(t.id, setTimeout(() => settle(t.id), SETTLE_MS));
}
onBeforeUnmount(() => {
  for (const [id, timer] of timers) {
    clearTimeout(timer);
    settle(id);
  }
});

// ---- the new todo
const title = ref("");
const focused = ref(false);
/** The chosen reminder time, null for none; the quick key it came from, or the custom panel. */
const at = ref<number | null>(null);
const quick = ref<string | null>(null);
const custom = ref(false);
const repeat = ref<TodoRepeat>("none");
/** The bar under the new line shows while it is being written. */
const writing = computed(() => focused.value || !!title.value.trim() || at.value != null || custom.value);
const quicks = computed(() => quickTimes(todoNow.value));
const days = computed(() => dayStrip(todoNow.value));
// Opening the custom time shortens the list: it goes back to the top, so the overdue todos stay in view.
watch(custom, async () => {
  await nextTick();
  scroller.value?.scrollTo({ top: 0 });
  measure();
});
watch(() => [todos.value.length, doneShown.value], () => void nextTick(measure));

function clearTime() {
  at.value = null;
  quick.value = null;
  custom.value = false;
  repeat.value = "none";
}
function pickQuick(q: { key: string; at: number }) {
  if (quick.value === q.key) return clearTime();
  clearTime();
  quick.value = q.key;
  at.value = q.at;
}
/** The calendar key: opens the custom time (the next full hour, or the quick time chosen), or drops it. */
function toggleCustom() {
  if (custom.value) return clearTime();
  if (at.value == null) {
    const d = new Date(todoNow.value);
    at.value = timeAt(d.getTime(), 0, d.getHours() + 1, 0);
  }
  quick.value = null;
  custom.value = true;
}
const dayOff = computed(() => (at.value == null ? -1 : dayOffset(at.value, todoNow.value)));
function pickDay(off: number) {
  if (at.value == null) return;
  const d = new Date(at.value);
  at.value = timeAt(todoNow.value, off, d.getHours(), d.getMinutes());
}

type Part = "hour" | "minute";
const MIN_STEP = 5;
const two = (n: number) => String(n).padStart(2, "0");
const hh = computed(() => (at.value == null ? "" : two(new Date(at.value).getHours())));
const mm = computed(() => (at.value == null ? "" : two(new Date(at.value).getMinutes())));
function setPart(part: Part, value: number) {
  if (at.value == null) return;
  const d = new Date(at.value);
  if (part === "hour") d.setHours(((value % 24) + 24) % 24);
  else d.setMinutes(((value % 60) + 60) % 60);
  at.value = d.getTime();
}
/** Hours go round the day; minutes go by five round the hour. */
function step(part: Part, by: number) {
  if (at.value == null) return;
  const d = new Date(at.value);
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
    box.value?.focus();
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

function add() {
  const text = cleanTitle(title.value);
  if (!text) return;
  const time = at.value;
  if (time != null && settings.todoSound) wakeAudio();
  addTodo({ title: text, at: time, repeat: time == null ? "none" : repeat.value });
  title.value = "";
  clearTime();
  box.value?.focus();
}
function onEnter(e: KeyboardEvent) {
  // Enter that confirms an input method's word is not the add.
  if (e.isComposing || e.keyCode === 229) return;
  add();
}
/** Esc drops what is being written first, then closes the page. */
function onEsc() {
  if (title.value || at.value != null || custom.value) {
    title.value = "";
    clearTime();
    box.value?.focus();
  } else {
    emit("done");
  }
}

// ---- typing: from the first focus on a text box until the page closes, the overlay can take the keyboard. Kept for
// the page's lifetime: taken back on a box's blur, a press elsewhere on the page could deactivate the window and close it.
let typing = false;
async function onFocusIn(e: FocusEvent) {
  const target = e.target as HTMLElement | null;
  if (typing || target?.tagName !== "INPUT") return;
  typing = true;
  await setOverlayTyping(true);
  // The press that focused the box came before the window could take keys.
  if (typing && document.activeElement !== target) target.focus();
}
onBeforeUnmount(() => {
  if (!typing) return;
  typing = false;
  void setOverlayTyping(false);
});

type Switch = "todoSound" | "todoNotify";
const SWITCHES: { key: Switch; on: string; off: string; label: string }[] = [
  { key: "todoSound", on: "sound", off: "mute", label: "提示音" },
  { key: "todoNotify", on: "bell", off: "bell-off", label: "系统通知" },
];
function flip(key: Switch) {
  settings[key] = !settings[key];
  // Turning the tune on plays it once, so it is heard before it is needed.
  if (key === "todoSound" && settings[key]) {
    wakeAudio();
    pomodoroTune("rest");
  }
}
</script>

<template>
  <div
    ref="root" class="todo-dock" :class="{ up, picking: writing && custom }" :style="[lift, { '--shift': `${shift}px` }]"
    role="group" aria-label="待办" data-hit data-no-drag @keydown.esc.stop="onEsc" @focusin="onFocusIn"
  >
    <header class="head">
      <b>待办</b>
      <span v-if="open.length" class="count">{{ open.length }}</span>
      <span class="toggles">
        <button
          v-for="s in SWITCHES" :key="s.key" type="button" class="toggle" :title="s.label" :aria-label="s.label"
          :aria-pressed="settings[s.key]" @click="flip(s.key)"
        >
          <Icon :name="settings[s.key] ? s.on : s.off" :size="15" />
        </button>
      </span>
    </header>

    <div
      v-if="open.length || done.length" ref="scroller" class="scroll"
      :class="{ 'cut-top': cut.top, 'cut-bottom': cut.bottom }" @scroll.passive="measure"
    >
      <TransitionGroup tag="ul" name="row" class="list">
        <li
          v-for="t in open" :key="t.id" class="row" :class="{ ticking: settling.has(t.id) }"
          :title="t.title.length > 14 ? t.title : undefined"
        >
          <button
            type="button" class="tick" :aria-pressed="settling.has(t.id)" :aria-label="`完成 ${t.title}`" @click="tick(t)"
          >
            <Icon name="check" :size="11" />
          </button>
          <span class="text">
            <span class="name">{{ t.title }}</span>
            <small v-if="t.at != null" :class="{ late: late(t) }">
              {{ whenText(t.at, todoNow) }}
              <Icon v-if="t.repeat !== 'none'" name="refresh" :size="10" />
            </small>
          </span>
          <button type="button" class="del" :aria-label="`删除 ${t.title}`" @click="removeTodo(t.id)">
            <Icon name="close" :size="12" />
          </button>
        </li>
      </TransitionGroup>
      <template v-if="done.length">
        <button type="button" class="fold" :aria-expanded="doneShown" @click="toggleDone">
          <Icon name="down" :size="12" />
          <span>已完成</span>
          <b>{{ done.length }}</b>
        </button>
        <ul v-if="doneShown" class="list">
          <li v-for="t in done" :key="t.id" class="row done" :title="t.title.length > 14 ? t.title : undefined">
            <button type="button" class="tick" aria-pressed="true" :aria-label="`完成 ${t.title}`" @click="tick(t)">
              <Icon name="check" :size="11" />
            </button>
            <span class="text"><span class="name">{{ t.title }}</span></span>
            <button type="button" class="del" :aria-label="`删除 ${t.title}`" @click="removeTodo(t.id)">
              <Icon name="close" :size="12" />
            </button>
          </li>
        </ul>
      </template>
    </div>

    <div class="new" :class="{ writing }">
      <label class="row add">
        <span class="plus" aria-hidden="true"><Icon name="plus" :size="11" /></span>
        <input
          ref="box" v-model="title" class="box" type="text" :maxlength="TITLE_MAX" placeholder="添加待办"
          enterkeyhint="done" @keydown.enter="onEnter" @focus="focused = true" @blur="focused = false"
        />
      </label>
      <div v-if="writing" class="quick">
        <button
          v-for="q in quicks" :key="q.key" type="button" class="chip" :aria-pressed="quick === q.key"
          @mousedown.prevent @click="pickQuick(q)"
        >
          {{ q.label }}
        </button>
        <button
          type="button" class="chip cal" :aria-pressed="custom" aria-label="自定时间" @mousedown.prevent @click="toggleCustom"
        >
          <Icon name="calendar" :size="14" />
        </button>
      </div>
      <div v-if="writing && custom && at != null" class="custom">
        <div class="days" role="radiogroup" aria-label="日期">
          <button
            v-for="d in days" :key="d.off" type="button" class="day" role="radio" :aria-checked="dayOff === d.off"
            @mousedown.prevent @click="pickDay(d.off)"
          >
            <small>{{ d.label }}</small><b>{{ d.date }}</b>
          </button>
        </div>
        <div class="when">
          <Icon name="clock" :size="14" />
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
        </div>
        <div class="seg" role="radiogroup" aria-label="重复">
          <button
            v-for="r in REPEATS" :key="r" type="button" role="radio" :aria-checked="repeat === r"
            @mousedown.prevent @click="repeat = r"
          >
            {{ REPEAT_LABEL[r] }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The paper plate of the quick emotes: a title line, the list, and the new line at the bottom. */
.todo-dock {
  position: absolute;
  left: 50%;
  top: calc(100% + 10px);
  transform: translateX(calc(-50% + var(--shift, 0px)));
  z-index: 20;
  display: flex;
  flex-direction: column;
  width: 300px;
  padding: 6px;
  box-sizing: border-box;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 8px 20px -6px rgba(var(--shadow-rgb), 0.35);
  font-family: var(--font);
  color: var(--ink);
  animation: drop-in var(--dur-base) var(--ease-out);
  cursor: default;
}
.todo-dock.up {
  top: auto;
  bottom: calc(100% + 10px);
  animation-name: rise-in;
}

/* Title and open count on the left, the two switches as small icons on the right. */
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 2px 0 8px;
}
.head > b {
  font: 800 var(--fs-body)/1 var(--font);
}
.count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  box-sizing: border-box;
  border-radius: 9px;
  background: var(--c-100);
  color: var(--c-600);
  text-align: center;
  font: 800 12px/18px var(--font-latin);
  font-variant-numeric: tabular-nums;
}
.toggles {
  display: flex;
  gap: 2px;
  margin-left: auto;
}
.toggle {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.toggle:hover {
  background: var(--c-50);
  color: var(--ink-2);
}
.toggle[aria-pressed="true"] {
  color: var(--c-600);
}

/* About five lines show; more scroll inside, so the new line stays in view. */
.scroll {
  max-height: 196px;
  overflow-y: auto;
  scrollbar-width: thin;
  overscroll-behavior: contain;
}
/* Rows cut off at an edge fade out there, so a half row reads as more to scroll. */
.scroll.cut-top {
  mask-image: linear-gradient(to bottom, transparent, #000 18px);
}
.scroll.cut-bottom {
  mask-image: linear-gradient(to top, transparent, #000 18px);
}
.scroll.cut-top.cut-bottom {
  mask-image: linear-gradient(to bottom, transparent, #000 18px, #000 calc(100% - 18px), transparent);
}
/* With the custom time open the list gives up room, so the plate stays on screen. */
.todo-dock.picking .scroll {
  max-height: 118px;
}
.list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 38px;
  padding: 0 4px 0 8px;
  border-radius: 9px;
  transition: background var(--dur-fast);
}
.list .row:hover {
  background: var(--c-50);
}
.tick {
  flex: none;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 2px solid var(--c-300);
  border-radius: 50%;
  background: transparent;
  color: transparent;
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}
.tick:hover {
  border-color: var(--c-500);
  color: var(--c-300);
}
.tick[aria-pressed="true"] {
  border-color: var(--c-500);
  background: var(--c-500);
  color: var(--surface);
}
.text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 13px/1.25 var(--font);
  transition: color var(--dur-fast);
}
.text small {
  display: flex;
  align-items: center;
  gap: 3px;
  font: 700 11px/1 var(--font);
  font-variant-numeric: tabular-nums;
  color: var(--ink-3);
}
.text small.late {
  color: var(--c-600);
}
.row.ticking .name, .row.done .name {
  color: var(--ink-3);
  text-decoration: line-through;
  text-decoration-color: var(--c-300);
}
.del {
  flex: none;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ink-3);
  opacity: 0;
  cursor: pointer;
  transition: opacity var(--dur-fast), background var(--dur-fast), color var(--dur-fast);
}
.row:hover .del, .del:focus-visible {
  opacity: 1;
}
.del:hover {
  background: var(--surface);
  color: var(--ink);
}
/* A ticked todo slides off towards the ticked-off group. */
.row-leave-active {
  transition: opacity var(--dur-base) var(--ease-in), transform var(--dur-base) var(--ease-in);
}
.row-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* The ticked-off group: a fold line with its count; folded at first. */
.fold {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 30px;
  margin-top: 2px;
  padding: 0 8px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--ink-3);
  font: 700 var(--fs-label)/1 var(--font);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.fold:hover {
  background: var(--c-50);
  color: var(--ink-2);
}
.fold .icon {
  rotate: -90deg;
  transition: rotate var(--dur-fast) var(--ease-out);
}
.fold[aria-expanded="true"] .icon {
  rotate: 0deg;
}
.fold b {
  font: 800 12px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}

/* The new line: the list's last line, a plus where the tick would be. */
.new {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 2px;
  padding-top: 2px;
  border-top: 1px solid var(--c-100);
}
.row.add {
  cursor: text;
}
.plus {
  flex: none;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  color: var(--ink-3);
  transition: color var(--dur-fast);
}
.new.writing .plus {
  color: var(--c-600);
}
.box {
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font: 700 13px/1 var(--font);
  user-select: text;
  -webkit-user-select: text;
}
.box::placeholder {
  color: var(--ink-3);
}

/* Quick times under the line while it is written: flat tiles, tinted while chosen. */
.quick {
  display: flex;
  gap: 4px;
  padding: 0 2px;
}
.chip {
  flex: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 9px;
  background: var(--c-50);
  color: var(--ink-2);
  font: 700 var(--fs-label)/1 var(--font);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.chip:hover {
  background: var(--c-100);
  color: var(--ink);
}
.chip[aria-pressed="true"] {
  background: var(--c-100);
  color: var(--ink);
  box-shadow: inset 0 0 0 1.5px var(--c-500);
}
.chip.cal {
  flex: none;
  width: 34px;
  padding: 0;
}
.chip.cal[aria-pressed="true"] .icon {
  color: var(--c-600);
}

/* The custom time: a week of dates, the hour and minute boxes, the repeat choice. */
.custom {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 2px 2px;
  padding: 6px;
  border-radius: 12px;
  background: var(--c-50);
}
.days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}
.day {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 5px 0 4px;
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
.when {
  display: flex;
  align-items: center;
  gap: 3px;
  padding-left: 4px;
  color: var(--ink-3);
}
.when .icon {
  margin-right: 2px;
}
.when i {
  font: 800 14px/1 var(--font-latin);
  font-style: normal;
}
.num {
  width: 30px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  outline: none;
  background: var(--surface);
  color: var(--ink);
  text-align: center;
  font: 800 15px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  user-select: text;
  -webkit-user-select: text;
  transition: box-shadow var(--dur-fast);
}
.num:focus {
  box-shadow: inset 0 0 0 1.5px var(--c-500);
}
/* The repeat choice: a small segmented control. */
.seg {
  display: flex;
  padding: 2px;
  border-radius: 8px;
  background: var(--c-100);
}
.seg button {
  flex: auto;
  height: 24px;
  padding: 0 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--ink-3);
  font: 700 11px/1 var(--font);
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
@media (prefers-reduced-motion: reduce) {
  .row-leave-active { transition: none; }
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
