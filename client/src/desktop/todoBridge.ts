// The todos' own window in the app: it shows the desk window's list, which the desk sends on every change
// (desktop/bridge.ts), and asks the desk for each change (stores/todo.ts). Only the settings and the todos come over:
// this window loads none of the desk's network stores.
import { listen } from "@tauri-apps/api/event";
import { isTauri } from "../composables/tauri";
import type { Settings } from "../stores/settings";
import { todos } from "../stores/todo";
import type { Todo } from "../todo";
import { syncSettings } from "./settingsSync";
import { requestDesktop } from "./transport";

export async function initTodoWindow(): Promise<() => void> {
  if (!isTauri) return () => {};
  const unTodos = await listen<Todo[]>("desktop:todos", ({ payload }) => { todos.value = payload; }, { target: "todo" });
  const synced = await syncSettings();
  const initial = await requestDesktop<{ settings: Settings; todos: Todo[] }>("todoSync");
  synced.apply(initial.settings);
  todos.value = initial.todos;
  return () => { unTodos(); synced.stop(); };
}
