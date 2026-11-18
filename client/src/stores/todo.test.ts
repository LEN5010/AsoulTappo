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
  const clock = await import("./todoClock");
  stops.push(nudge.startNudges(() => false, () => clock.todosWaiting()));
  if (!away) nudge.noteNudgeInput();
  stops.push(clock.startTodoClock());
  return { nudge, store, clock };
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
  store.addTodo({ title: "交周报", at: START + 10 * MIN, allDay: false, repeat: "none" });
  await busy(nudge, 10 * MIN);
  const id = store.todos.value[0].id;
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "交周报", todo: id });
  store.finishTodo(id);
  expect(store.todos.value[0].doneAt).not.toBeNull();
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", reply: true });
});

it("waits while the player is away and goes up when they are back", async () => {
  const { nudge, store, clock } = await desk(undefined, true);
  store.addTodo({ title: "开会", at: START + MIN, allDay: false, repeat: "none" });
  await vi.advanceTimersByTimeAsync(2 * MIN);
  expect(nudge.nudge.value).toBeNull();
  expect(clock.todosWaiting()).toBe(true);
  nudge.noteNudgeInput();
  await vi.advanceTimersByTimeAsync(5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "开会" });
});

it("puts the todos missed while the app was closed into one bubble", async () => {
  const saved = [newTodo("a", "a", { at: START - 60 * MIN, allDay: false, repeat: "none" }, 0),
    newTodo("b", "b", { at: START - 30 * MIN, allDay: false, repeat: "none" }, 0)];
  const { nudge } = await desk(saved, true);
  nudge.noteNudgeInput();
  await vi.advanceTimersByTimeAsync(5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todos", text: "有 2 条待办过时了" });
});

it("takes the place of a water reminder but not of the tomato timer's question", async () => {
  const { nudge, store } = await desk();
  nudge.nudge.value = { kind: "tip", tip: "water", text: "记得喝水哦" };
  store.addTodo({ title: "取快递", at: START + MIN, allDay: false, repeat: "none" });
  await busy(nudge, MIN);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "取快递" });

  nudge.offerPomodoro("again", "休息好啦");
  store.addTodo({ title: "回消息", at: START + 90_000, allDay: false, repeat: "none" });
  await busy(nudge, 40_000);
  expect(nudge.nudge.value?.kind).toBe("again");
  nudge.closeNudge();
  await busy(nudge, 5000);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "回消息" });
});

it("snoozes from the bubble and rings again ten minutes later", async () => {
  const { nudge, store } = await desk();
  store.addTodo({ title: "吃药", at: START + MIN, allDay: false, repeat: "none" });
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
  store.addTodo({ title: "a", at: null, allDay: false, repeat: "none" });
  const saved = JSON.parse(localStorage.getItem("asoultappo.todos")!);
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ title: "a", at: null });
});

it("changes the title and the time from another window's request, and the moved todo's bubble goes", async () => {
  const { nudge, store } = await desk();
  store.addTodo({ title: "取快递", at: START + MIN, allDay: false, repeat: "none" });
  await busy(nudge, MIN);
  const id = store.todos.value[0].id;
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", todo: id });
  store.todoRequest("rename", [id, "  取 快递 "]);
  expect(store.todos.value[0].title).toBe("取 快递");
  store.todoRequest("retime", [id, { at: START + 60 * MIN, allDay: false, repeat: "daily" }]);
  expect(store.todos.value[0]).toMatchObject({ at: START + 60 * MIN, repeat: "daily", rang: null });
  expect(nudge.nudge.value).toBeNull();
});

it("follows the list written by the browser preview's other window", async () => {
  const listeners: ((e: { key: string }) => void)[] = [];
  vi.stubGlobal("window", {
    addEventListener: (type: string, cb: (e: { key: string }) => void) => { if (type === "storage") listeners.push(cb); },
    removeEventListener: () => {},
  });
  const { nudge, store } = await desk();
  store.addTodo({ title: "交周报", at: START + MIN, allDay: false, repeat: "none" });
  await busy(nudge, MIN);
  expect(nudge.nudge.value).toMatchObject({ kind: "todo", text: "交周报" });
  // The popup ticks it off and writes the list.
  const written = store.todos.value.map((t) => ({ ...t, doneAt: Date.now() }));
  localStorage.setItem("asoultappo.todos", JSON.stringify(written));
  listeners.forEach((cb) => cb({ key: "asoultappo.todos" }));
  expect(store.todos.value[0].doneAt).not.toBeNull();
  expect(nudge.nudge.value).toBeNull();
});

it("keeps a reminder that waited for the player across a restart, and shows it once without ringing again", async () => {
  const sfx = await import("../audio/sfx");
  const tune = vi.spyOn(sfx, "pomodoroTune").mockImplementation(() => {});
  const first = await desk(undefined, true);
  first.store.addTodo({ title: "开会", at: START + MIN, allDay: false, repeat: "none" });
  await vi.advanceTimersByTimeAsync(MIN + 5000);
  // Away: the bubble cannot go up, the todo waits.
  expect(first.nudge.nudge.value).toBeNull();
  expect(first.clock.todosWaiting()).toBe(true);
  expect(tune).toHaveBeenCalledTimes(1);
  // The app quits and starts again.
  stops.forEach((stop) => stop());
  stops = [];
  vi.resetModules();
  const tuneAgain = vi.spyOn(await import("../audio/sfx"), "pomodoroTune").mockImplementation(() => {});
  const again = await desk(undefined, true);
  expect(again.clock.todosWaiting()).toBe(true);
  again.nudge.noteNudgeInput();
  await vi.advanceTimersByTimeAsync(5000);
  expect(again.nudge.nudge.value).toMatchObject({ kind: "todo", text: "开会" });
  expect(tuneAgain).not.toHaveBeenCalled();
  expect(again.clock.todosWaiting()).toBe(false);
  // Shown once: after the bubble is answered nothing waits any more, also after another restart.
  stops.forEach((stop) => stop());
  stops = [];
  vi.resetModules();
  const third = await desk();
  await vi.advanceTimersByTimeAsync(5000);
  expect(third.clock.todosWaiting()).toBe(false);
  expect(third.nudge.nudge.value).toBeNull();
});

it("drops a kept wait whose todo was ticked off or removed before the restart", async () => {
  const first = await desk(undefined, true);
  first.store.addTodo({ title: "a", at: START + MIN, allDay: false, repeat: "none" });
  await vi.advanceTimersByTimeAsync(MIN + 5000);
  expect(first.clock.todosWaiting()).toBe(true);
  const saved = JSON.parse(localStorage.getItem("asoultappo.todos")!);
  stops.forEach((stop) => stop());
  stops = [];
  vi.resetModules();
  // Ticked off in the list before the app started again.
  localStorage.setItem("asoultappo.todos", JSON.stringify(saved.map((t: object) => ({ ...t, doneAt: START }))));
  const again = await desk();
  expect(again.clock.todosWaiting()).toBe(false);
  await vi.advanceTimersByTimeAsync(5000);
  expect(again.nudge.nudge.value).toBeNull();
});
