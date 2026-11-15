// The bubble over the own pet for reminders (src/nudge.ts has the timing) and the tomato timer (stores/pomodoro.ts):
// one at a time, gone by itself after a while.
import { ref } from "vue";
import {
  LINES, LUNCH_ASK, LUNCH_REPLY, NIGHT_LINES, NudgeClock, greetLine, minuteOfDay, pick, type NudgeDays, type NudgeKind,
} from "../nudge";
import type { PomodoroBubble } from "../pomodoro";
import { drank } from "./room";
import { settings } from "./settings";

export interface Nudge {
  kind: NudgeKind | PomodoroBubble;
  text: string;
  /** The answer to the lunch question, shown briefly without keys. */
  reply?: boolean;
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

function textOf(kind: NudgeKind, now: number): string {
  if (kind === "lunch") return LUNCH_ASK;
  if (kind === "greet") return greetLine(minuteOfDay(now), Math.random);
  if (kind === "night") return pick(NIGHT_LINES, Math.random);
  return pick(LINES[kind], Math.random);
}

function show(kind: NudgeKind, now: number) {
  nudge.value = { kind, text: textOf(kind, now) };
  close(SHOW_MS);
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

/** A rest of the tomato timer began: it is the break the sitting reminder asks for, bubble or not. */
export function notePomodoroRest() {
  clock?.shown("move", Date.now());
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
  const c = (clock = new NudgeClock(Date.now(), Math.random, loadDays()));
  held = holdAll;
  const tick = () => {
    const now = Date.now();
    // Counted while switched off or held back too; only the showing waits.
    const kind = c.due(now);
    if (!kind || !settings.healthTips || nudge.value || holdAll() || holdReminders()) return;
    show(kind, now);
    c.shown(kind, now);
    if (kind === "lunch" || kind === "greet" || kind === "night") saveDay(kind, c.days[kind]);
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
