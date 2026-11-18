// The bubble over the own pet for reminders (src/nudge.ts has the timing, src/reminders.ts the player's own list), the
// tomato timer (stores/pomodoro.ts) and todos (stores/todo.ts): one at a time, gone by itself after a while.
import { ref } from "vue";
import { isPanelWindow } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import {
  LUNCH_ASK, LUNCH_REPLY, NIGHT_LINES, NudgeClock, greetLine, minuteOfDay, pick, type Due, type NudgeDays, type NudgeKind,
} from "../nudge";
import type { PomodoroBubble } from "../pomodoro";
import { linesOf, type Reminder } from "../reminders";
import { drank } from "./room";
import { settings } from "./settings";

/** A todo that came due (`todo`), or several at once (`todos`, a key opens the list). */
export type TodoBubble = "todo" | "todos";

export interface Nudge {
  kind: NudgeKind | PomodoroBubble | TodoBubble;
  text: string;
  /** The answer to the lunch question or a todo ticked off, shown briefly without keys. */
  reply?: boolean;
  /** The todo of a `todo` bubble. */
  todo?: string;
  /** The reminder of a `tip` bubble (a Reminder's id). */
  tip?: string;
}

export const nudge = ref<Nudge | null>(null);
/** Size of the bubble (NudgeBubble.vue), for placing it on screen. */
export const NUDGE_WIDTH = 220;
export const NUDGE_HEIGHT = 52;

const TICK_MS = 30_000;
const SHOW_MS = 30_000;
const REPLY_MS = 3500;
/** The question whether to go again waits longer: unanswered, the timer stays stopped. */
const AGAIN_MS = 60_000;
const DAY_KEYS: Record<keyof NudgeDays, string> = {
  lunch: "asoultappo.nudge.lunch", greet: "asoultappo.nudge.greet", night: "asoultappo.nudge.night",
};

let clock: NudgeClock | null = null;
let held: () => boolean = () => false;
let closeTimer: ReturnType<typeof setTimeout> | undefined;

/** Input from the global hook (and, in the browser preview, the page): the player is at the computer. */
export function noteNudgeInput() {
  clock?.input(Date.now());
}

function close(after: number) {
  clearTimeout(closeTimer);
  closeTimer = setTimeout(() => { nudge.value = null; }, after);
}

export function closeNudge() {
  clearTimeout(closeTimer);
  nudge.value = null;
}

export function answerLunch(ate: boolean) {
  nudge.value = { kind: "lunch", text: pick(ate ? LUNCH_REPLY.ate : LUNCH_REPLY.notYet, Math.random), reply: true };
  close(REPLY_MS);
}

/** The water reminder answered: the player drank, which the room sees too. */
export function drankWater() {
  closeNudge();
  drank();
}

function textOf(due: Due, now: number): string {
  if (due.tip) return pick(linesOf(due.tip), Math.random);
  if (due.kind === "lunch") return LUNCH_ASK;
  if (due.kind === "greet") return greetLine(minuteOfDay(now), Math.random);
  return pick(NIGHT_LINES, Math.random);
}

function show(due: Due, now: number) {
  nudge.value = { kind: due.kind, text: textOf(due, now), tip: due.tip?.id };
  close(due.tip ? due.tip.showSec * 1000 : SHOW_MS);
}

/**
 * Shows [reminder] over the pet now, as it would come up, for trying it out from its settings. Nothing is counted;
 * it gives way to anything else over the pet.
 */
export function tryReminder(reminder: Reminder) {
  if (isPanelWindow) { void requestDesktop("tryReminder", reminder); return; }
  if (held() || keepsSpot(nudge.value)) return;
  show({ kind: "tip", tip: reminder }, Date.now());
}

/**
 * A bubble of the tomato timer, shown now unless something else holds the spot over the pet (a reminder or an earlier
 * bubble of the timer gives way to it); whether it went up. Closing by itself answers nothing: an unanswered question
 * leaves the timer as it is.
 */
export function offerPomodoro(kind: PomodoroBubble, text: string): boolean {
  if (held()) return false;
  nudge.value = { kind, text };
  close(kind === "again" ? AGAIN_MS : SHOW_MS);
  clock?.mark(Date.now());
  return true;
}

const POMODORO: readonly string[] = ["rest", "back", "again"] satisfies PomodoroBubble[];
/** The bubble up is the tomato timer's, or a todo's or the lunch question that still waits for an answer. */
const keepsSpot = (n: Nudge | null) =>
  !!n && (POMODORO.includes(n.kind) || (["todo", "todos", "lunch"].includes(n.kind) && !n.reply));

/** The player is away from the computer; true while the reminders' clock is not running. */
export const playerAway = () => (clock ? clock.away(Date.now()) : true);

/**
 * A todo's bubble, shown now unless something else holds the spot over the pet, the tomato timer or another todo has
 * the bubble, the lunch question waits for an answer, or the player is away; whether it went up. It takes the place
 * of the other reminders (the player's own, hello, bedtime).
 */
export function offerTodo(kind: TodoBubble, text: string, todo?: string): boolean {
  if (held() || keepsSpot(nudge.value) || playerAway()) return false;
  nudge.value = { kind, text, todo };
  close(SHOW_MS);
  clock?.mark(Date.now());
  return true;
}

/** Todo [id] was ticked off: the pet says a short line, in place of that todo's bubble or where the spot is free. */
export function sayTodoDone(text: string, id: string) {
  if (held() || (keepsSpot(nudge.value) && nudge.value?.todo !== id)) return;
  nudge.value = { kind: "todo", text, reply: true };
  close(REPLY_MS);
}

/** A rest of the tomato timer began: it is the break the reminders to get up ask for, bubble or not. */
export function notePomodoroRest() {
  clock?.rested();
}

function loadDays(): NudgeDays {
  const days: NudgeDays = {};
  for (const [kind, key] of Object.entries(DAY_KEYS) as [keyof NudgeDays, string][]) {
    try { days[kind] = localStorage.getItem(key) ?? ""; } catch { /* storage unavailable */ }
  }
  return days;
}

function saveDay(kind: keyof NudgeDays, day: string) {
  try { localStorage.setItem(DAY_KEYS[kind], day); } catch { /* storage unavailable */ }
}

/**
 * Starts the clock. [holdAll] is true while something else is over the pet or the pet is hidden, and holds the timer's
 * bubbles too; [holdReminders] holds the reminders only (the tomato timer's focus).
 */
export function startNudges(holdAll: () => boolean, holdReminders: () => boolean = () => false): () => void {
  const c = (clock = new NudgeClock(Date.now(), Math.random, loadDays(), () => settings.reminders,
    () => ({ greet: settings.tipGreet, lunch: settings.tipLunch, night: settings.tipNight })));
  held = holdAll;
  const tick = () => {
    const now = Date.now();
    // Counted while switched off or held back too; only the showing waits.
    const due = c.due(now);
    if (!due || !settings.healthTips || nudge.value || holdAll() || holdReminders()) return;
    show(due, now);
    c.shown(due, now);
    if (due.kind !== "tip") saveDay(due.kind, c.days[due.kind]);
  };
  const timer = setInterval(tick, TICK_MS);
  const events = ["pointermove", "pointerdown", "keydown"] as const;
  for (const e of events) window.addEventListener(e, noteNudgeInput, { passive: true });
  return () => {
    clearInterval(timer);
    for (const e of events) window.removeEventListener(e, noteNudgeInput);
    closeNudge();
    if (clock === c) {
      clock = null;
      held = () => false;
    }
  };
}
