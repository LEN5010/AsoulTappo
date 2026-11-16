<script setup lang="ts">
// The todos' own window (`?window=todo`): a small card on a transparent window, kept over other windows unless
// unpinned (src-tauri/src/lib.rs, open_todo). The title bar moves it and holds the switches for the tune, the system
// notice and the pin. The list shows the overdue todos first, then today's, the later ones and the untimed ones;
// the ticked-off ones fold under it. The bar at the bottom adds a todo; its time and repeat keys open the time
// picker and the repeat menu above it. The list itself is the desk window's (stores/todo.ts).
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { LogicalSize } from "@tauri-apps/api/dpi";
import {
  NO_WHEN, REPEATS, REPEAT_LABEL, TITLE_MAX, cleanTitle, doneTodos, sortTodos, whenOf, whenText, type Todo, type TodoRepeat,
  type TodoWhen,
} from "./todo";
import { addTodo, editWhen, finishTodo, removeTodo, todoNow, todos, undoTodo } from "./stores/todo";
import { settings, todoSize } from "./stores/settings";
import { pomodoroTune, wakeAudio } from "./audio/sfx";
import { isTauri } from "./composables/tauri";
import Icon from "./ui/Icon.vue";
import TodoRow from "./todos/TodoRow.vue";
import WhenPicker from "./todos/WhenPicker.vue";

/** In the browser preview the page floats in a frame over the desk page (pet/TodoFrame.vue), which moves and hides it. */
const framed = !isTauri && window.parent !== window;
type FrameMessage = { type: "todo:hide" } | { type: "todo:move"; dx: number; dy: number } | { type: "todo:size"; w: number; h: number };
const toFrame = (message: FrameMessage) =>
  window.parent.postMessage(message, location.origin);
if (!isTauri) document.documentElement.classList.add("browser-preview");
if (framed) document.documentElement.classList.add("framed");

// ---- the clock: the desk's ticks do not reach this window
const CLOCK_MS = 15_000;
const now = () => { todoNow.value = Date.now(); };
let clock: ReturnType<typeof setInterval> | undefined;

// ---- the list
const open = computed(() => sortTodos(todos.value.filter((t) => t.doneAt == null), todoNow.value));
const done = computed(() => doneTodos(todos.value));
const doneShown = ref(false);

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
function remove(t: Todo) {
  if (picker.value === t.id) picker.value = null;
  removeTodo(t.id);
}

// ---- the new todo
const title = ref("");
const box = ref<HTMLInputElement>();
const draft = ref<TodoWhen>({ ...NO_WHEN });
const hasText = computed(() => !!title.value.trim());
function send() {
  const text = cleanTitle(title.value);
  if (!text) return;
  addTodo({ title: text, ...draft.value });
  title.value = "";
  draft.value = { ...NO_WHEN };
  closePops();
  box.value?.focus();
}
function onEnter(e: KeyboardEvent) {
  // Enter that confirms an input method's word is not the add.
  if (e.isComposing || e.keyCode === 229) return;
  send();
}

// ---- the time picker and the repeat menu: for the new todo ("new") or a todo of the list (its id)
const picker = ref<string | null>(null);
const repeatOpen = ref(false);
const picked = computed(() => (picker.value && picker.value !== "new" ? todos.value.find((t) => t.id === picker.value) : null));
const pickerValue = computed(() => (picker.value === "new" ? draft.value : picked.value ? whenOf(picked.value) : NO_WHEN));
function onPick(when: TodoWhen) {
  if (picker.value === "new") draft.value = when;
  else if (picked.value) editWhen(picked.value.id, when);
}
// A todo ticked off or removed meanwhile closes its picker.
watch(picked, (t) => { if (picker.value && picker.value !== "new" && (!t || t.doneAt != null)) picker.value = null; });
/** While a todo of the list is being retimed, the list makes room under it so the todo can stay above the picker. */
const scroller = ref<HTMLElement>();
const room = ref(0);
async function togglePicker(target: string) {
  repeatOpen.value = false;
  picker.value = picker.value === target ? null : target;
  room.value = 0;
  if (!picker.value || picker.value === "new") return;
  await nextTick();
  const list = scroller.value;
  const row = list?.querySelector(`[data-id="${CSS.escape(target)}"]`);
  const pop = document.querySelector(".when-picker");
  if (!list || !row || !pop) return;
  const top = pop.getBoundingClientRect().top - 6;
  room.value = Math.max(0, list.getBoundingClientRect().bottom - top);
  await nextTick();
  const over = row.getBoundingClientRect().bottom - top;
  if (over > 0) list.scrollBy({ top: over, behavior: "smooth" });
}
watch(picker, (p) => { if (!p || p === "new") room.value = 0; });
function clearWhen(id: string) {
  editWhen(id, NO_WHEN);
  picker.value = null;
}
/** The repeat menu stands over its key, which moves right once the time is set. */
const repeatKey = ref<HTMLElement>();
const menuLeft = ref(8);
function toggleRepeat() {
  picker.value = null;
  repeatOpen.value = !repeatOpen.value;
  const key = repeatKey.value?.parentElement;
  if (key) menuLeft.value = key.offsetLeft;
}
/** A repeat without a day starts today, as a whole day. */
function pickRepeat(r: TodoRepeat) {
  const d = draft.value;
  draft.value = d.at == null && r !== "none" ? { at: todoNow.value, allDay: true, repeat: r } : { ...d, repeat: r };
  repeatOpen.value = false;
  box.value?.focus();
}
function closePops() {
  picker.value = null;
  repeatOpen.value = false;
}
/** A press outside the picker, the menu and the keys that open them closes them. */
function onPointerDown(e: PointerEvent) {
  const t = e.target as HTMLElement | null;
  if (!t?.closest?.(".when-picker, .repeat-menu, [data-pop]")) closePops();
}

// ---- the window
function drag(e: PointerEvent) {
  if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
  if (isTauri) return void getCurrentWindow().startDragging();
  if (!framed) return;
  // The frame moves under the pointer, so the steps are taken on the screen.
  const head = e.currentTarget as HTMLElement;
  head.setPointerCapture(e.pointerId);
  let x = e.screenX;
  let y = e.screenY;
  const move = (m: PointerEvent) => {
    toFrame({ type: "todo:move", dx: m.screenX - x, dy: m.screenY - y });
    x = m.screenX;
    y = m.screenY;
  };
  const end = () => {
    head.removeEventListener("pointermove", move);
    head.removeEventListener("pointerup", end);
    head.removeEventListener("pointercancel", end);
  };
  head.addEventListener("pointermove", move);
  head.addEventListener("pointerup", end);
  head.addEventListener("pointercancel", end);
}
/** The grip at the bottom right corner sizes the window, taken on the screen as the window grows under the pointer. */
function resize(e: PointerEvent) {
  if (e.button !== 0 || (!isTauri && !framed)) return;
  e.preventDefault();
  closePops();
  const grip = e.currentTarget as HTMLElement;
  grip.setPointerCapture(e.pointerId);
  const x0 = e.screenX;
  const y0 = e.screenY;
  const w0 = window.innerWidth;
  const h0 = window.innerHeight;
  let size = { w: w0, h: h0 };
  let pending = 0;
  const apply = () => {
    pending = 0;
    if (isTauri) void getCurrentWindow().setSize(new LogicalSize(size.w, size.h)).catch(() => {});
    else toFrame({ type: "todo:size", ...size });
  };
  const move = (m: PointerEvent) => {
    size = { w: todoSize(w0 + m.screenX - x0, "w"), h: todoSize(h0 + m.screenY - y0, "h") };
    if (!pending) pending = requestAnimationFrame(apply);
  };
  const end = () => {
    grip.removeEventListener("pointermove", move);
    grip.removeEventListener("pointerup", end);
    grip.removeEventListener("pointercancel", end);
    if (pending) { cancelAnimationFrame(pending); apply(); }
    settings.todoW = size.w;
    settings.todoH = size.h;
  };
  grip.addEventListener("pointermove", move);
  grip.addEventListener("pointerup", end);
  grip.addEventListener("pointercancel", end);
}
function hide() {
  closePops();
  if (isTauri) void invoke("hide_todo");
  else if (framed) toFrame({ type: "todo:hide" });
  else window.close();
}
/** Esc closes the picker or the menu first, then drops what is being written, then hides the window. */
function onEsc() {
  if (picker.value || repeatOpen.value) return closePops();
  if (title.value) {
    title.value = "";
    draft.value = { ...NO_WHEN };
    return;
  }
  hide();
}
function onWindowFocus() {
  now();
  if (!document.activeElement || document.activeElement === document.body) box.value?.focus();
}

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
function flipPin() {
  settings.todoPinned = !settings.todoPinned;
  if (isTauri) void invoke("set_todo_on_top", { on: settings.todoPinned });
}

onMounted(async () => {
  clock = setInterval(now, CLOCK_MS);
  window.addEventListener("focus", onWindowFocus);
  document.addEventListener("pointerdown", onPointerDown, true);
  box.value?.focus();
  // Created hidden; shown once mounted, as the panel is (a hidden page gets no animation frames to wait for).
  if (isTauri) await invoke("show_todo").catch(() => {});
  box.value?.focus();
});
onBeforeUnmount(() => {
  clearInterval(clock);
  window.removeEventListener("focus", onWindowFocus);
  document.removeEventListener("pointerdown", onPointerDown, true);
  for (const [id, timer] of timers) {
    clearTimeout(timer);
    settle(id);
  }
});
</script>

<template>
  <div class="todo-window" @keydown.esc="onEsc">
    <section class="card" aria-label="待办">
      <header class="head" @pointerdown="drag">
        <b>待办</b>
        <span v-if="open.length" class="count">{{ open.length }}</span>
        <span class="keys">
          <button
            v-for="s in SWITCHES" :key="s.key" type="button" class="key" :title="s.label" :aria-label="s.label"
            :aria-pressed="settings[s.key]" @click="flip(s.key)"
          >
            <Icon :name="settings[s.key] ? s.on : s.off" :size="15" />
          </button>
          <button
            type="button" class="key pin" title="置顶" aria-label="置顶" :aria-pressed="settings.todoPinned" @click="flipPin"
          >
            <Icon name="pin" :size="15" />
          </button>
          <button type="button" class="key" title="关闭" aria-label="关闭" @click="hide">
            <Icon name="close" :size="15" />
          </button>
        </span>
      </header>

      <div ref="scroller" class="scroll" :style="room ? { paddingBottom: `${room}px` } : undefined">
        <div v-if="!open.length && !done.length" class="empty" aria-hidden="true">
          <Icon name="todo" :size="48" />
        </div>
        <TransitionGroup tag="ul" name="row" class="list">
          <TodoRow
            v-for="t in open" :key="t.id" :data-id="t.id" :todo="t" :now="todoNow" :ticking="settling.has(t.id)" :picking="picker === t.id"
            @tick="tick(t)" @remove="remove(t)" @when="togglePicker(t.id)" @clear-when="clearWhen(t.id)"
          />
        </TransitionGroup>
        <template v-if="done.length">
          <button type="button" class="fold" :aria-expanded="doneShown" @click="doneShown = !doneShown">
            <Icon name="down" :size="12" />
            <span>已完成</span>
            <b>{{ done.length }}</b>
          </button>
          <ul v-if="doneShown" class="list">
            <TodoRow v-for="t in done" :key="t.id" :todo="t" :now="todoNow" @tick="tick(t)" @remove="remove(t)" />
          </ul>
        </template>
      </div>

      <footer class="composer">
        <WhenPicker
          v-if="picker" class="pop" :model-value="pickerValue" :now="todoNow" :repeat="picker !== 'new'"
          @update:model-value="onPick"
        />
        <div v-if="repeatOpen" class="repeat-menu pop-menu" role="menu" aria-label="重复" :style="{ left: `${menuLeft}px` }">
          <button
            v-for="r in REPEATS" :key="r" type="button" role="menuitemradio" :aria-checked="draft.repeat === r"
            @click="pickRepeat(r)"
          >
            <span>{{ REPEAT_LABEL[r] }}</span>
            <Icon class="mark" name="check" :size="13" />
          </button>
        </div>

        <div class="field">
          <input
            ref="box" v-model="title" class="box" type="text" :maxlength="TITLE_MAX" placeholder="添加待办"
            enterkeyhint="send" aria-label="添加待办" @keydown.enter="onEnter"
          />
          <button type="button" class="send" :class="{ on: hasText }" title="添加" aria-label="添加" @click="send">
            <Icon name="send" :size="15" />
          </button>
        </div>
        <div class="opts">
          <span class="opt-pair" :class="{ set: draft.at != null }">
            <button
              type="button" class="opt" data-pop title="时间" aria-label="时间" :aria-expanded="picker === 'new'"
              @click="togglePicker('new')"
            >
              <Icon name="calendar" :size="14" />
              <span v-if="draft.at != null">{{ whenText(draft.at, draft.allDay, todoNow) }}</span>
            </button>
            <button
              v-if="draft.at != null" type="button" class="opt-x" aria-label="清除时间"
              @click="draft = { ...NO_WHEN }; picker = null"
            >
              <Icon name="close" :size="11" />
            </button>
          </span>
          <span class="opt-pair" :class="{ set: draft.repeat !== 'none' }">
            <button
              ref="repeatKey" type="button" class="opt" data-pop title="重复" aria-label="重复" :aria-expanded="repeatOpen"
              @click="toggleRepeat"
            >
              <Icon name="refresh" :size="14" />
              <span v-if="draft.repeat !== 'none'">{{ REPEAT_LABEL[draft.repeat] }}</span>
            </button>
          </span>
        </div>
      </footer>
      <span class="grip" aria-hidden="true" @pointerdown="resize"></span>
    </section>
  </div>
</template>

<style>
html, body, #app { margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }
body { font-family: var(--font); color: var(--ink); -webkit-font-smoothing: antialiased; }
/* The browser preview's popup: a soft desk behind the card. */
html.browser-preview body { background: linear-gradient(160deg, #e9edf3, #f3e3e8); }
/* In a frame over the desk page only the card shows. */
html.browser-preview.framed body { background: transparent; }
</style>

<style scoped>
/* The window is transparent: the card stands inside it with room for its shadow. */
.todo-window {
  position: fixed;
  inset: 0;
  padding: 8px;
  box-sizing: border-box;
  -webkit-user-select: none;
  user-select: none;
}
/* The corner that sizes the window: two short strokes, darker under the pointer. */
.grip {
  position: absolute;
  right: 0;
  bottom: 0;
  z-index: 5;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  touch-action: none;
  background:
    linear-gradient(135deg, transparent 50%, var(--c-300) 50%, var(--c-300) 58%, transparent 58%,
      transparent 70%, var(--c-300) 70%, var(--c-300) 78%, transparent 78%);
  border-bottom-right-radius: var(--radius-l);
}
.grip:hover {
  background:
    linear-gradient(135deg, transparent 50%, var(--c-500) 50%, var(--c-500) 58%, transparent 58%,
      transparent 70%, var(--c-500) 70%, var(--c-500) 78%, transparent 78%);
}
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 6px 16px -6px rgba(var(--shadow-rgb), 0.32);
}

/* The title bar moves the window: title and open count on the left, small icon keys on the right. */
.head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 44px;
  padding: 0 6px 0 16px;
  cursor: grab;
}
.head:active {
  cursor: grabbing;
}
.head > b {
  font: 800 var(--fs-strong)/1 var(--font);
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
.keys {
  display: flex;
  gap: 1px;
  margin-left: auto;
}
.key {
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
.key:hover {
  background: var(--c-50);
  color: var(--ink-2);
}
.key[aria-pressed="true"] {
  color: var(--c-600);
}
.key.pin .icon {
  rotate: 30deg;
  transition: rotate var(--dur-fast) var(--ease-out);
}
.key.pin[aria-pressed="true"] .icon {
  rotate: 0deg;
}

/* The list scrolls between the title bar and the bar at the bottom. */
.scroll {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 6px 6px;
  scrollbar-width: thin;
  overscroll-behavior: contain;
}
.empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--c-100);
  pointer-events: none;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* A ticked todo slides off towards the ticked-off group. */
.row-leave-active {
  transition: opacity var(--dur-base) var(--ease-in), transform var(--dur-base) var(--ease-in);
}
.row-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
.row-move {
  transition: transform var(--dur-base) var(--ease-out);
}

/* The ticked-off group: a fold line with its count; folded at first. */
.fold {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 32px;
  margin-top: 4px;
  padding: 0 10px;
  border: 0;
  border-radius: 10px;
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

/* The bar at the bottom: the line with its send key, the time and repeat keys under it. */
.composer {
  position: relative;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--c-50);
}
.pop, .pop-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  z-index: 5;
  animation: pop-in var(--dur-base) var(--ease-out);
}
.pop {
  left: 6px;
  right: 6px;
  max-height: calc(100vh - 154px);
  box-sizing: border-box;
  overflow-y: auto;
}
@keyframes pop-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
.field {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 38px;
  padding: 0 4px 0 12px;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.08);
}
.box {
  flex: 1;
  min-width: 0;
  height: 100%;
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
.send {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: color-mix(in oklab, var(--ink-3) 22%, var(--surface));
  color: var(--surface);
  cursor: default;
  transition: background var(--dur-fast), transform var(--dur-release) var(--ease-spring);
}
.send.on {
  background: var(--c-500);
  cursor: pointer;
}
.send.on:hover {
  background: var(--c-600);
}
.send.on:active {
  transform: scale(0.92);
}

/* The time and repeat keys: small tiles; set, they show the value tinted, the time with its clear key. */
.opts {
  display: flex;
  gap: 6px;
}
.opt-pair {
  display: flex;
  align-items: center;
  height: 26px;
  border-radius: 8px;
  transition: background var(--dur-fast);
}
.opt-pair.set {
  background: var(--c-100);
}
.opt {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  min-width: 30px;
  justify-content: center;
  padding: 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink-3);
  font: 700 var(--fs-label)/1 var(--font);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.opt:hover, .opt[aria-expanded="true"] {
  background: var(--c-100);
  color: var(--ink-2);
}
.opt-pair.set .opt {
  color: var(--c-700);
}
.opt-pair.set .opt:hover, .opt-pair.set .opt[aria-expanded="true"] {
  background: var(--c-200);
}
.opt-x {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin: 0 3px 0 -3px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--c-700);
  cursor: pointer;
}
.opt-x:hover {
  background: var(--c-200);
}

/* The repeat menu over its key. */
.repeat-menu {
  display: flex;
  flex-direction: column;
  gap: 1px;
  width: 132px;
  padding: 4px;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.1), 0 10px 28px -8px rgba(var(--shadow-rgb), 0.32);
}
.repeat-menu button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  font: 700 var(--fs-body)/1 var(--font);
  cursor: pointer;
}
.repeat-menu button:hover {
  background: var(--c-50);
}
.repeat-menu .mark {
  color: var(--c-600);
  opacity: 0;
}
.repeat-menu button[aria-checked="true"] .mark {
  opacity: 1;
}
</style>
