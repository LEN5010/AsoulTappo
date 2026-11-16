import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { newTodo } from "../todo";

const MIN = 60_000;
const START = new Date(2026, 10, 16, 8, 0).getTime();
let stops: (() => void)[] = [];

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.setSystemTime(START);
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, v: string) => saved.set(key, v),
    removeItem: (key: string) => saved.delete(key),
  });
  vi.stubGlobal("window", { addEventListener: () => {}, removeEventListener: () => {} });
});
afterEach(() => {
  stops.forEach((stop) => stop());
  stops = [];
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** The desk's clocks started, with the player at the computer unless `away`. */
async function desk(saved?: unknown[], away = false) {
  if (saved) localStorage.setItem("asoultappo.todos", JSON.stringify(saved));
  const nudge = await import("./nudge");
  const store = await import("./todo");
  stops.push(nudge.startNudges(() => false, () => store.todosWaiting()));
  if (!away) nudge.noteNudgeInput();
  stops.push(store.startTodoClock());
  return { nudge, store };
}

/** Time passing with the player at the computer: input every few seconds. */
async function busy(nudge: typeof import("./nudge"), ms: number) {
  for (let left = ms; left > 0; left -= 5000) {
    nudge.noteNudgeInput();
    await vi.advanceTimersByTimeAsync(Math.min(5000, left));
  }
}

it("puts a todo that comes due over the pet, and the pet answers its tick", async () => {
  const { nudge, store } = await desk();
  store.addTodo({ title: "交周报", at: START + 10 * MIN, repeat: "none" });
  await busy(nudge, 10 * MIN);
  const id = store.todos.value[0].id;
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "交周报", todo: id });
  store.finishTodo(id);
  expect(store.todos.value[0].doneAt).not.toBeNull();
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", reply: true });
});

it("waits while the player is away and goes up when they are back", async () => {
  const { nudge, store } = await desk(undefined, true);
  store.addTodo({ title: "开会", at: START + MIN, repeat: "none" });
  await vi.advanceTimersByTimeAsync(2 * MIN);
  expect(nudge.nudge.value).toBeNull();
  expect(store.todosWaiting()).toBe(true);
  nudge.noteNudgeInput();
  await vi.advanceTimersByTimeAsync(5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "开会" });
});

it("puts the todos missed while the app was closed into one bubble", async () => {
  const saved = [newTodo("a", "a", START - 60 * MIN, "none", 0), newTodo("b", "b", START - 30 * MIN, "none", 0)];
  const { nudge } = await desk(saved, true);
  nudge.noteNudgeInput();
  await vi.advanceTimersByTimeAsync(5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todos", text: "有 2 条待办过时了" });
});

it("takes the place of a water reminder but not of the tomato timer's question", async () => {
  const { nudge, store } = await desk();
  nudge.nudge.value = { kind: "water", text: "记得喝水哦" };
  store.addTodo({ title: "取快递", at: START + MIN, repeat: "none" });
  await busy(nudge, MIN);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "取快递" });

  nudge.offerPomodoro("again", "休息好啦");
  store.addTodo({ title: "回消息", at: START + 90_000, repeat: "none" });
  await busy(nudge, 40_000);
  expect(nudge.nudge.value?.kind).toBe("again");
  nudge.closeNudge();
  await busy(nudge, 5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "回消息" });
});

it("snoozes from the bubble and rings again ten minutes later", async () => {
  const { nudge, store } = await desk();
  store.addTodo({ title: "吃药", at: START + MIN, repeat: "none" });
  await busy(nudge, MIN);
  store.laterTodo(store.todos.value[0].id);
  expect(nudge.nudge.value).toBeNull();
  await busy(nudge, 9 * MIN);
  expect(nudge.nudge.value).toBeNull();
  await busy(nudge, MIN + 5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "吃药" });
});

it("keeps the list across restarts", async () => {
  const { store } = await desk();
  store.addTodo({ title: "a", at: null, repeat: "none" });
  const saved = JSON.parse(localStorage.getItem("asoultappo.todos")!);
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ title: "a", at: null });
});
