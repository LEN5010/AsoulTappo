// The own pet's todos (src/todo.ts has the rules), kept on this device by the desk window. The desk's clock and the
// bubble over the pet are in stores/todoClock.ts. The todos' own window and the panel show the desk window's copy and
// change it there (desktop/bridge.ts, desktop/todoBridge.ts); in the browser preview the todos' popup and the desk share
// the stored list and follow each other's writes through the storage event.
//
// No import of the nudge or room stores here: the todos' window loads this module, and those start desk work.
import { ref } from "vue";
import { isPanelWindow, isTauri, isTodoWindow } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import {
  MAX_TODOS, completeTodo, newTodo, readTodos, renameTodo, reopenTodo, retimeTodo, snoozeTodo, type Todo, type TodoWhen,
} from "../todo";

export const TODOS_KEY = "asoultappo.todos";

function load(): Todo[] {
  try {
    const raw = localStorage.getItem(TODOS_KEY);
    return raw ? readTodos(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

/** The list lives in another window: the panel and the todos' window of the app ask the desk for each change. */
const remote = isPanelWindow || (isTauri && isTodoWindow);

export const todos = ref<Todo[]>(remote ? [] : load());
/** The clock the lists are drawn from: the desk's ticks move it, the todos' window has its own (TodoApp.vue). */
export const todoNow = ref(Date.now());

/** What the desk does over the pet when a todo changes; stores/todoClock.ts fills these in. */
export const todoHooks = {
  /** Ticked off: the pet says a line in place of its bubble. */
  done: (_id: string) => {},
  /** Gone, moved to another time or snoozed: its bubble and its wait for one end. */
  dropped: (_id: string) => {},
  /** The list was changed by another window of the browser preview. */
  synced: () => {},
};

export function setTodos(list: Todo[]) {
  todos.value = list;
  if (remote) return;
  try {
    localStorage.setItem(TODOS_KEY, JSON.stringify(list));
  } catch { /* storage unavailable */ }
}

const change = (id: string, fn: (t: Todo) => Todo) => setTodos(todos.value.map((t) => (t.id === id ? fn(t) : t)));

export type TodoMethod = "add" | "complete" | "reopen" | "remove" | "snooze" | "rename" | "retime";
export type TodoDraft = TodoWhen & { title: string };

/** The desk window's side of a change asked for by another window (desktop/bridge.ts). */
export function todoRequest(method: TodoMethod, arg: unknown) {
  if (method === "add") addTodo(arg as TodoDraft);
  else if (method === "complete") finishTodo(arg as string);
  else if (method === "reopen") undoTodo(arg as string);
  else if (method === "remove") removeTodo(arg as string);
  else if (method === "snooze") laterTodo(arg as string);
  else if (method === "rename") { const [id, title] = arg as [string, string]; renameOne(id, title); }
  else if (method === "retime") { const [id, when] = arg as [string, TodoWhen]; retimeOne(id, when); }
}

export function addTodo(draft: TodoDraft) {
  if (remote) { void requestDesktop("todo", "add", draft); return; }
  const t = newTodo(crypto.randomUUID(), draft.title, draft, Date.now());
  if (!t.title) return;
  // Past the limit the oldest ticked-off ones make room; a list of open ones only takes no more.
  const list = [...todos.value];
  while (list.length >= MAX_TODOS) {
    const done = list.reduce<number>((best, x, i) =>
      (x.doneAt != null && (best < 0 || x.doneAt < list[best].doneAt!) ? i : best), -1);
    if (done < 0) return;
    list.splice(done, 1);
  }
  setTodos([...list, t]);
}

/** Ticked off, from the list or the bubble: the pet says a line in place of the todo's bubble. */
export function finishTodo(id: string) {
  if (remote) { void requestDesktop("todo", "complete", id); return; }
  const t = todos.value.find((x) => x.id === id);
  if (!t || t.doneAt != null) return;
  change(id, (x) => completeTodo(x, Date.now()));
  todoHooks.done(id);
}

export function undoTodo(id: string) {
  if (remote) { void requestDesktop("todo", "reopen", id); return; }
  change(id, reopenTodo);
}

export function removeTodo(id: string) {
  if (remote) { void requestDesktop("todo", "remove", id); return; }
  setTodos(todos.value.filter((t) => t.id !== id));
  todoHooks.dropped(id);
}

/** The bubble's later key: reminded again in ten minutes. */
export function laterTodo(id: string) {
  if (remote) { void requestDesktop("todo", "snooze", id); return; }
  change(id, (t) => snoozeTodo(t, Date.now()));
  todoHooks.dropped(id);
}

/** A new title; an empty one keeps the old. */
export function editTitle(id: string, title: string) {
  if (remote) { void requestDesktop("todo", "rename", [id, title]); return; }
  renameOne(id, title);
}
function renameOne(id: string, title: string) {
  change(id, (t) => renameTodo(t, title));
}

/** A new time, day or repeat, or none. */
export function editWhen(id: string, when: TodoWhen) {
  if (remote) { void requestDesktop("todo", "retime", [id, when]); return; }
  retimeOne(id, when);
}
function retimeOne(id: string, when: TodoWhen) {
  const t = todos.value.find((x) => x.id === id);
  if (!t || t.doneAt != null) return;
  change(id, (x) => retimeTodo(x, when, Date.now()));
  todoHooks.dropped(id);
}

// The browser preview: the todos' popup and the desk are two pages of one origin, and each writes the stored list.
if (!isTauri && typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("storage", (e) => {
    if (e.key !== TODOS_KEY) return;
    todos.value = load();
    todoHooks.synced();
  });
}
