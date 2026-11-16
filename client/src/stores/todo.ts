// The own pet's todos (src/todo.ts has the rules), kept on this device by the desk window. Their reminders go up over
// the own pet through stores/nudge.ts, with the tomato timer's tune and an optional system notice. The panel shows the
// desk window's copy and changes it there (desktop/bridge.ts).
import { ref, watch } from "vue";
import { isPanelWindow, notify } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { pomodoroTune } from "../audio/sfx";
import {
  DONE_LINES, MAX_TODOS, completeTodo, newTodo, readTodos, reopenTodo, snoozeTodo, stepTodos, type Todo, type TodoRepeat,
} from "../todo";
import { pick } from "../nudge";
import { closeNudge, nudge, offerTodo, sayTodoDone } from "./nudge";
import { settings } from "./settings";

const KEY = "asoultappo.todos";
const TICK_MS = 5000;

function load(): Todo[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? readTodos(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

export const todos = ref<Todo[]>(isPanelWindow ? [] : load());
/** The clock the lists are drawn from; it moves with the desk window's ticks, so today's view follows midnight. */
export const todoNow = ref(Date.now());
/** Todos that rang and wait for the spot over the pet; `late` ones rang after their time had passed unseen. */
let waiting: { id: string; late: boolean }[] = [];

function set(list: Todo[]) {
  todos.value = list;
  if (isPanelWindow) return;
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch { /* storage unavailable */ }
}

const change = (id: string, fn: (t: Todo) => Todo) => set(todos.value.map((t) => (t.id === id ? fn(t) : t)));
/** The bubble of todo [id] is up and asks for an answer. */
const bubbleOf = (id: string) => nudge.value?.kind === "todo" && nudge.value.todo === id && !nudge.value.reply;

export type TodoMethod = "add" | "complete" | "reopen" | "remove" | "snooze";
export interface TodoDraft { title: string; at: number | null; repeat: TodoRepeat }

/** The desk window's side of a change asked for by the panel (desktop/bridge.ts). */
export function todoRequest(method: TodoMethod, arg: unknown) {
  if (method === "add") addTodo(arg as TodoDraft);
  else if (method === "complete") finishTodo(arg as string);
  else if (method === "reopen") undoTodo(arg as string);
  else if (method === "remove") removeTodo(arg as string);
  else if (method === "snooze") laterTodo(arg as string);
}

export function addTodo(draft: TodoDraft) {
  if (isPanelWindow) { void requestDesktop("todo", "add", draft); return; }
  const t = newTodo(crypto.randomUUID(), draft.title, draft.at, draft.repeat, Date.now());
  if (!t.title) return;
  // Past the limit the oldest ticked-off ones make room; a list of open ones only takes no more.
  const list = [...todos.value];
  while (list.length >= MAX_TODOS) {
    const done = list.reduce<number>((best, x, i) =>
      (x.doneAt != null && (best < 0 || x.doneAt < list[best].doneAt!) ? i : best), -1);
    if (done < 0) return;
    list.splice(done, 1);
  }
  set([...list, t]);
}

/** Ticked off, from the list or the bubble: the pet says a line in place of the todo's bubble. */
export function finishTodo(id: string) {
  if (isPanelWindow) { void requestDesktop("todo", "complete", id); return; }
  const t = todos.value.find((x) => x.id === id);
  if (!t || t.doneAt != null) return;
  change(id, (x) => completeTodo(x, Date.now()));
  waiting = waiting.filter((w) => w.id !== id);
  sayTodoDone(pick(DONE_LINES, Math.random), id);
}

export function undoTodo(id: string) {
  if (isPanelWindow) { void requestDesktop("todo", "reopen", id); return; }
  change(id, reopenTodo);
}

export function removeTodo(id: string) {
  if (isPanelWindow) { void requestDesktop("todo", "remove", id); return; }
  set(todos.value.filter((t) => t.id !== id));
  waiting = waiting.filter((w) => w.id !== id);
  if (bubbleOf(id)) closeNudge();
}

/** The bubble's later key: reminded again in ten minutes. */
export function laterTodo(id: string) {
  if (isPanelWindow) { void requestDesktop("todo", "snooze", id); return; }
  change(id, (t) => snoozeTodo(t, Date.now()));
  if (bubbleOf(id)) closeNudge();
}

/** Todos are waiting for the spot over the pet: the water and sitting reminders let them go first. */
export const todosWaiting = () => waiting.length > 0;

/** One waiting todo gets its own bubble; several share one that opens the list. */
function offer() {
  const open = new Map(todos.value.filter((t) => t.doneAt == null).map((t) => [t.id, t]));
  waiting = waiting.filter((w) => open.has(w.id));
  if (!waiting.length) return;
  const shown = waiting.length === 1
    ? offerTodo("todo", open.get(waiting[0].id)!.title, waiting[0].id)
    : offerTodo("todos", waiting.every((w) => w.late) ? `有 ${waiting.length} 条待办过时了` : `有 ${waiting.length} 条待办到时间了`);
  if (shown) waiting = [];
}

function tick() {
  const now = Date.now();
  todoNow.value = now;
  const { list, onTime, late } = stepTodos(todos.value, now);
  if (list !== todos.value) set(list);
  if (onTime.length) {
    if (settings.todoSound) pomodoroTune("rest");
    if (settings.todoNotify) for (const t of onTime) void notify("待办", t.title);
  }
  for (const t of [...onTime, ...late]) {
    if (!waiting.some((w) => w.id === t.id)) waiting.push({ id: t.id, late: late.includes(t) });
  }
  offer();
}

/** Notices switched on send one at once, like the tomato timer's: the system asks the first time; refused, the switch goes off. */
async function noticesOn(on: boolean) {
  if (on && !(await notify("待办", "待办到时间时会在这里提醒"))) settings.todoNotify = false;
}

/** The desk window's clock: rings what comes due, also what passed while the app was closed or the computer slept. */
export function startTodoClock(): () => void {
  tick();
  const timer = setInterval(tick, TICK_MS);
  const stopNotices = watch(() => settings.todoNotify, (on) => void noticesOn(on));
  return () => { clearInterval(timer); stopNotices(); waiting = []; };
}
