// The desk window's side of the todos (stores/todo.ts): the clock that rings what comes due, and the bubble over the
// own pet through stores/nudge.ts, with the tomato timer's tune and an optional system notice.
import { watch } from "vue";
import { notify } from "../composables/tauri";
import { pomodoroTune } from "../audio/sfx";
import { DONE_LINES, stepTodos } from "../todo";
import { pick } from "../nudge";
import { closeNudge, nudge, offerTodo, sayTodoDone } from "./nudge";
import { settings } from "./settings";
import { setTodos, todoHooks, todoNow, todos } from "./todo";

const TICK_MS = 5000;
const WAITING_KEY = "asoultappo.todos.waiting";

interface Waiting { id: string; late: boolean }
/**
 * Todos that rang and wait for the spot over the pet; `late` ones rang after their time had passed unseen. Kept with
 * the list: a ring is marked in the list (`rang`) when it happens, so a wait lost on quitting would never come back.
 */
let waiting: Waiting[] = [];

function keepWaiting(next: Waiting[]) {
  if (next.length === waiting.length && next.every((w, i) => w.id === waiting[i].id && w.late === waiting[i].late)) return;
  waiting = next;
  try {
    if (next.length) localStorage.setItem(WAITING_KEY, JSON.stringify(next));
    else localStorage.removeItem(WAITING_KEY);
  } catch { /* storage unavailable */ }
}

/** The waits kept from the last run, for todos still open. */
function loadWaiting(): Waiting[] {
  try {
    const raw = JSON.parse(localStorage.getItem(WAITING_KEY) ?? "[]") as unknown;
    if (!Array.isArray(raw)) return [];
    const open = new Set(todos.value.filter((t) => t.doneAt == null).map((t) => t.id));
    return raw.filter((w): w is Waiting => !!w && typeof w.id === "string" && open.has(w.id))
      .map((w) => ({ id: w.id, late: w.late === true }));
  } catch {
    return [];
  }
}

/** The bubble of todo [id] is up and asks for an answer. */
const bubbleOf = (id: string) => nudge.value?.kind === "todo" && nudge.value.todo === id && !nudge.value.reply;

function drop(id: string) {
  keepWaiting(waiting.filter((w) => w.id !== id));
  if (bubbleOf(id)) closeNudge();
}

/** Todos are waiting for the spot over the pet: the water and sitting reminders let them go first. */
export const todosWaiting = () => waiting.length > 0;

/** One waiting todo gets its own bubble; several share one that opens the todos' window. */
function offer() {
  const open = new Map(todos.value.filter((t) => t.doneAt == null).map((t) => [t.id, t]));
  keepWaiting(waiting.filter((w) => open.has(w.id)));
  if (!waiting.length) return;
  const shown = waiting.length === 1
    ? offerTodo("todo", open.get(waiting[0].id)!.title, waiting[0].id)
    : offerTodo("todos", waiting.every((w) => w.late) ? `有 ${waiting.length} 条待办过时了` : `有 ${waiting.length} 条待办到时间了`);
  if (shown) keepWaiting([]);
}

function tick() {
  const now = Date.now();
  todoNow.value = now;
  const { list, onTime, late } = stepTodos(todos.value, now);
  if (list !== todos.value) setTodos(list);
  if (onTime.length) {
    if (settings.todoSound) pomodoroTune("rest");
    if (settings.todoNotify) for (const t of onTime) void notify("待办", t.title);
  }
  const rung = [...onTime, ...late].filter((t) => !waiting.some((w) => w.id === t.id));
  if (rung.length) keepWaiting([...waiting, ...rung.map((t) => ({ id: t.id, late: late.includes(t) }))]);
  offer();
}

/** Notices switched on send one at once, like the tomato timer's: the system asks the first time; refused, the switch goes off. */
async function noticesOn(on: boolean) {
  if (on && !(await notify("待办", "待办到时间时会在这里提醒"))) settings.todoNotify = false;
}

/** The desk window's clock: rings what comes due, also what passed while the app was closed or the computer slept. */
export function startTodoClock(): () => void {
  todoHooks.done = (id) => {
    keepWaiting(waiting.filter((w) => w.id !== id));
    sayTodoDone(pick(DONE_LINES, Math.random), id);
  };
  todoHooks.dropped = drop;
  // Changed in the browser preview's popup: a todo ticked off, removed or moved there loses its bubble here.
  todoHooks.synced = () => {
    const n = nudge.value;
    if (n?.kind === "todo" && n.todo && !n.reply) {
      const t = todos.value.find((x) => x.id === n.todo);
      if (!t || t.doneAt != null || t.rang == null) closeNudge();
    }
  };
  // Rang before the app last quit and never shown: they go up again; their tune and notice went out back then.
  waiting = loadWaiting();
  tick();
  const timer = setInterval(tick, TICK_MS);
  const stopNotices = watch(() => settings.todoNotify, (on) => void noticesOn(on));
  return () => {
    clearInterval(timer);
    stopNotices();
    waiting = [];
    todoHooks.done = todoHooks.dropped = () => {};
    todoHooks.synced = () => {};
  };
}
