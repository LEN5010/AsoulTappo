// The tomato timer of the desk window (src/pomodoro.ts has the timing). It is kept across restarts; its bubbles go
// up over the own pet through stores/nudge.ts. The panel shows it from the desk window's copy and starts or stops it
// there (desktop/bridge.ts).
import { computed, ref, watch } from "vue";
import { isMirrorWindow, notify } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { pomodoroDone, pomodoroLine, pomodoroNotice, readPomodoro, startPomodoro, stepPomodoro, type Pomodoro, type PomodoroBubble, type PomodoroPlan } from "../pomodoro";
import { pomodoroTune, wakeAudio } from "../audio/sfx";
import { closeNudge, notePomodoroRest, nudge, offerPomodoro } from "./nudge";
import { settings } from "./settings";

const KEY = "asoultappo.pomodoro";
const TICK_MS = 1000;

function load(): Pomodoro | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? readPomodoro(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

export const pomodoro = ref<Pomodoro | null>(load());
/** The clock the countdown is drawn from; it moves only while the timer runs. */
const now = ref(Date.now());
export const pomodoroLeft = computed(() => (pomodoro.value ? Math.max(0, pomodoro.value.until - now.value) : 0));
/** How much of the phase has gone, 0 to 1, for the ring on the timer's page. */
export const pomodoroProgress = computed(() => (pomodoro.value ? pomodoroDone(pomodoro.value, now.value) : 0));
/** In the focus part: the reminders wait. */
export const focusing = computed(() => pomodoro.value?.phase === "focus");
/** A bubble the timer asked for while something else held the spot over the pet. */
let waiting: { kind: PomodoroBubble; text: string } | null = null;
/** The round the last run ended on, so going again after the question keeps counting towards the long rest. */
let lastRound = 0;

export const pomodoroPlan = (): PomodoroPlan => ({
  focusMin: settings.pomodoroFocus, restMin: settings.pomodoroRest, long: settings.pomodoroLong, auto: settings.pomodoroAuto,
});

function set(p: Pomodoro | null) {
  pomodoro.value = p;
  now.value = Date.now();
  try {
    if (p) localStorage.setItem(KEY, JSON.stringify(p));
    else localStorage.removeItem(KEY);
  } catch { /* storage unavailable */ }
}

/** The timer's own bubble is up: answering it or starting over replaces it. */
const OWN: readonly string[] = ["rest", "back", "again"] satisfies PomodoroBubble[];
const ownBubble = () => !!nudge.value && OWN.includes(nudge.value.kind);

function start(round: number) {
  waiting = null;
  if (ownBubble()) closeNudge();
  set(startPomodoro(Date.now(), pomodoroPlan(), round));
}

/** A new run from the first round: the strip's menu, the tray, the settings page. */
export function beginPomodoro() {
  if (isMirrorWindow) { void requestDesktop("beginPomodoro"); return; }
  start(1);
}

/** Going again after the question (a press in this window): the round count carries on. */
export function nextPomodoro() {
  wakeAudio();
  start(lastRound + 1);
}

export function endPomodoro() {
  if (isMirrorWindow) { void requestDesktop("endPomodoro"); return; }
  waiting = null;
  lastRound = 0;
  if (ownBubble()) closeNudge();
  set(null);
}

function tick() {
  if (!pomodoro.value && !waiting) return;
  const t = Date.now();
  now.value = t;
  const plan = pomodoroPlan();
  const before = pomodoro.value;
  const { pomodoro: next, bubble } = stepPomodoro(before, t, plan);
  if (next !== before) {
    if (!next && before) lastRound = before.round;
    set(next);
    // A phase that ended while the app was closed passes in silence.
    if (bubble && settings.pomodoroSound) pomodoroTune(bubble === "rest" ? "rest" : "focus");
    if (bubble === "rest") notePomodoroRest();
    if (bubble && settings.pomodoroNotify) void notify("番茄钟", pomodoroNotice(bubble, next, plan));
    waiting = bubble && { kind: bubble, text: pomodoroLine(bubble, next, plan) };
  }
  if (waiting && offerPomodoro(waiting.kind, waiting.text)) waiting = null;
}

/** A press anywhere on the desk while the timer runs: the tunes can play when its phase ends. */
export function notePomodoroPress() {
  if (pomodoro.value && settings.pomodoroSound) wakeAudio();
}

/**
 * Notices switched on (on the timer's page or the settings page) send one at once: the system asks for permission the
 * first time, and it shows what they look like. Where they are refused, the switch goes back off.
 */
async function noticesOn(on: boolean) {
  if (on && !(await notify("番茄钟", "专注和休息结束时会在这里提醒"))) settings.pomodoroNotify = false;
}

export function startPomodoroClock(): () => void {
  tick();
  const timer = setInterval(tick, TICK_MS);
  const stopNotices = watch(() => settings.pomodoroNotify, (on) => void noticesOn(on));
  return () => { clearInterval(timer); stopNotices(); };
}
