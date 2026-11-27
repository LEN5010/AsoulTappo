import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick, reactive } from "vue";
import { cleanGuide } from "../guide";

type Label = "main" | "panel" | "todo" | "race" | "ddz";
interface Message { from: Label; patch: Record<string, unknown> }

/**
 * The app's event bus between windows, delivering by hand: each message waits in one queue, in the order it was sent,
 * until `step` or `flush` hands it on.
 */
function bus() {
  const queue: { target: string; payload: Message }[] = [];
  const subscribers = new Map<string, (e: { payload: Message }) => void>();
  const sent: { target: string; payload: Message }[] = [];
  vi.doMock("@tauri-apps/api/event", () => ({
    listen: async (_name: string, fn: (e: { payload: Message }) => void, { target }: { target: string }) => {
      subscribers.set(target, fn);
      return () => subscribers.delete(target);
    },
    emitTo: async (target: string, _name: string, payload: Message) => {
      queue.push({ target, payload });
      sent.push({ target, payload });
    },
  }));
  const step = () => {
    const next = queue.shift();
    if (next) subscribers.get(next.target)?.({ payload: next.payload });
    return !!next;
  };
  return { sent, queue, step, flush: () => { while (step()); } };
}

async function make(label: Label) {
  vi.resetModules();
  const settings = reactive({
    petX: 20, feedbackText: "", favorites: [] as string[], showcase: [], reminders: [], skinNotes: {},
    guide: cleanGuide(undefined),
  });
  vi.doMock("../composables/tauri", () => ({ windowLabel: label }));
  vi.doMock("../stores/settings", () => ({ settings }));
  const { syncSettings } = await import("./settingsSync");
  const sync = await syncSettings();
  return { settings, ...sync };
}

async function windows() {
  const b = bus();
  const all = { main: await make("main"), panel: await make("panel"), todo: await make("todo"), race: await make("race"), ddz: await make("ddz") };
  return { ...b, ...all, every: Object.values(all) };
}

afterEach(() => {
  vi.doUnmock("@tauri-apps/api/event");
  vi.doUnmock("../composables/tauri");
  vi.doUnmock("../stores/settings");
  vi.unstubAllGlobals();
  vi.resetModules();
});

it("hands the desk's own change to every side window", async () => {
  const w = await windows();
  w.main.settings.petX = 300;
  await nextTick();
  w.flush();
  expect(w.every.map((x) => x.settings.petX)).toEqual([300, 300, 300, 300, 300]);
  expect(w.sent.map((m) => m.target).sort()).toEqual(["ddz", "panel", "race", "todo"]);
  w.every.forEach((x) => x.stop());
});

it("hands a side window's change to the desk and on to the other side windows, and sends nothing back out", async () => {
  const w = await windows();
  w.panel.settings.favorites.push("a");
  await nextTick();
  w.flush();
  await nextTick();
  expect(w.every.map((x) => x.settings.favorites)).toEqual(Array(5).fill(["a"]));
  // Only the desk passes patches on: a window that applied one does not send it again.
  expect(w.sent.filter((m) => m.payload.from !== "main").map((m) => m.target)).toEqual(["main"]);
  expect(w.sent.every((m) => m.payload.patch.favorites)).toBe(true);
  w.every.forEach((x) => x.stop());
});

it("sends only the fields that changed, and nothing for the same value again", async () => {
  const w = await windows();
  w.todo.settings.petX = 20;
  expect(w.sent).toEqual([]);
  w.todo.settings.feedbackText = "hi";
  await nextTick();
  expect(w.sent.map((m) => m.payload.patch)).toEqual([{ feedbackText: "hi" }]);
  w.flush();
  expect(w.every.map((x) => x.settings.feedbackText)).toEqual(Array(5).fill("hi"));
  w.every.forEach((x) => x.stop());
});

it("meets the guide's progress with the one here instead of replacing it", async () => {
  const w = await windows();
  w.panel.settings.guide.done.push("tap");
  w.main.settings.guide.done.push("draw");
  await nextTick();
  w.flush();
  for (const x of w.every) expect([...x.settings.guide.done].sort()).toEqual(["draw", "tap"]);
  w.every.forEach((x) => x.stop());
});

it("ends with one value everywhere when the pet is dragged while the panel puts it back", async () => {
  const w = await windows();
  w.main.settings.petX = 180;
  w.panel.settings.petX = -1;
  await nextTick();
  w.flush();
  await nextTick();
  // The desk took the drag first and the reset after it: the reset is where everyone ends.
  expect(w.every.map((x) => x.settings.petX)).toEqual([-1, -1, -1, -1, -1]);
  w.every.forEach((x) => x.stop());
});

it("ends with the desk's order when two side windows change the same field", async () => {
  const w = await windows();
  w.panel.settings.petX = 1;
  w.ddz.settings.petX = 2;
  await nextTick();
  w.flush();
  expect(w.every.map((x) => x.settings.petX)).toEqual([2, 2, 2, 2, 2]);
  w.every.forEach((x) => x.stop());
});

it("never takes a side window back to an older value of its own while newer ones are on their way", async () => {
  const w = await windows();
  const seen: string[] = [];
  const type = (text: string) => { w.panel.settings.feedbackText = text; };
  type("a");
  await nextTick();
  w.step(); // The desk takes "a" and confirms it to every side window.
  type("ab");
  await nextTick();
  type("abc");
  while (w.step()) seen.push(w.panel.settings.feedbackText);
  expect(seen.every((text) => text === "abc")).toBe(true);
  expect(w.every.map((x) => x.settings.feedbackText)).toEqual(Array(5).fill("abc"));
  w.every.forEach((x) => x.stop());
});

it("takes another window's change made after its own", async () => {
  const w = await windows();
  w.panel.settings.feedbackText = "mine";
  await nextTick();
  w.step();
  w.todo.settings.feedbackText = "theirs";
  w.flush();
  expect(w.every.map((x) => x.settings.feedbackText)).toEqual(Array(5).fill("theirs"));
  w.every.forEach((x) => x.stop());
});

describe("keeping the settings", () => {
  afterEach(() => { vi.useRealTimers(); });

  async function load(search: string) {
    vi.resetModules();
    const setItem = vi.fn();
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search } });
    vi.stubGlobal("localStorage", { getItem: () => null, setItem });
    const { settings } = await import("../stores/settings");
    return { settings, setItem };
  }

  it("in the app, only the desk writes them to storage", async () => {
    vi.useFakeTimers();
    const desk = await load("");
    desk.settings.petX = 40;
    await vi.advanceTimersByTimeAsync(200);
    expect(desk.setItem).toHaveBeenCalledTimes(1);
    for (const side of ["panel", "todo", "race", "ddz"]) {
      const mirror = await load(`?window=${side}`);
      mirror.settings.petX = 41;
      await vi.advanceTimersByTimeAsync(200);
      expect(mirror.setItem).not.toHaveBeenCalled();
    }
  });

  it("in the browser preview, every page still writes them", async () => {
    vi.useFakeTimers();
    vi.resetModules();
    const setItem = vi.fn();
    vi.stubGlobal("window", { location: { search: "?window=todo" }, addEventListener() {} });
    vi.stubGlobal("localStorage", { getItem: () => null, setItem });
    const { settings } = await import("../stores/settings");
    settings.petX = 42;
    await vi.advanceTimersByTimeAsync(200);
    expect(setItem).toHaveBeenCalledTimes(1);
  });
});
