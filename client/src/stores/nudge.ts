// The reminder over the own pet (src/nudge.ts has the timing): one at a time, gone by itself after a while.
import { ref } from "vue";
import { LINES, LUNCH_ASK, LUNCH_REPLY, NudgeClock, pick, type NudgeKind } from "../nudge";
import { settings } from "./settings";

export interface Nudge {
  kind: NudgeKind;
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
const LUNCH_KEY = "asoultappo.nudge.lunch";

let clock: NudgeClock | null = null;
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

function show(kind: NudgeKind) {
  nudge.value = { kind, text: kind === "lunch" ? LUNCH_ASK : pick(LINES[kind], Math.random) };
  close(SHOW_MS);
}

/** Starts the clock; `held` is true while something else is over the pet or the pet is hidden. */
export function startNudges(held: () => boolean): () => void {
  let lunchDay = "";
  try { lunchDay = localStorage.getItem(LUNCH_KEY) ?? ""; } catch { /* storage unavailable */ }
  const c = (clock = new NudgeClock(Date.now(), Math.random, lunchDay));
  const tick = () => {
    const now = Date.now();
    // Counted while switched off or held back too; only the showing waits.
    const kind = c.due(now);
    if (!kind || !settings.healthTips || nudge.value || held()) return;
    show(kind);
    c.shown(kind, now);
    if (kind === "lunch") {
      try { localStorage.setItem(LUNCH_KEY, c.askedLunch); } catch { /* storage unavailable */ }
    }
  };
  const timer = setInterval(tick, TICK_MS);
  const events = ["pointermove", "pointerdown", "keydown"] as const;
  for (const e of events) window.addEventListener(e, noteNudgeInput, { passive: true });
  return () => {
    clearInterval(timer);
    for (const e of events) window.removeEventListener(e, noteNudgeInput);
    closeNudge();
    if (clock === c) clock = null;
  };
}
