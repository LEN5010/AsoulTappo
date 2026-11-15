// The tomato timer: a focus, then a rest, every few rounds a longer rest; then either the next focus starts by itself
// or the pet asks whether to go again. Pure timing: the caller steps it with the clock and the lengths set on the
// settings page, and shows the bubble `step` asks for over the own pet.

const MIN = 60_000;
/** Every this many focus rounds the rest is the long one (when long rests are on). */
export const LONG_EVERY = 4;
export const LONG_MIN = 15;

/** Lengths in minutes, from the settings page. */
export interface PomodoroPlan {
  focusMin: number;
  restMin: number;
  /** Long rests every LONG_EVERY rounds. */
  long: boolean;
  /** The next focus starts by itself after the rest; off, the pet asks first. */
  auto: boolean;
}

export const DEFAULT_PLAN: PomodoroPlan = { focusMin: 25, restMin: 5, long: true, auto: false };

export interface Pomodoro {
  phase: "focus" | "rest";
  /** Start and end of the phase, in ms since the epoch. */
  from: number;
  until: number;
  /** Focus rounds of this run so far, the current one included. */
  round: number;
  /** The rest is the long one. */
  long?: boolean;
}

/** Bubbles of the timer: focus is over (rest now), rest is over and the next focus started by itself, rest is over (go again?). */
export type PomodoroBubble = "rest" | "back" | "again";

/** A long rest is never shorter than the plain one. */
export const longRestMin = (plan: PomodoroPlan) => Math.max(LONG_MIN, plan.restMin);
const restMs = (plan: PomodoroPlan, long: boolean) => (long ? longRestMin(plan) : plan.restMin) * MIN;

export function pomodoroLine(bubble: PomodoroBubble, p: Pomodoro | null, plan: PomodoroPlan): string {
  if (bubble === "rest") return p?.long ? `专注完成，长休息 ${longRestMin(plan)} 分钟` : `专注完成，休息 ${plan.restMin} 分钟`;
  return bubble === "back" ? "休息结束，开始专注" : "休息好啦";
}

/** The system notice for a phase change; it cannot be answered, so the question to go again points to the pet. */
export function pomodoroNotice(bubble: PomodoroBubble, p: Pomodoro | null, plan: PomodoroPlan): string {
  return bubble === "again" ? "休息结束，可以再来一轮" : pomodoroLine(bubble, p, plan);
}

export const startPomodoro = (now: number, plan: PomodoroPlan, round = 1): Pomodoro =>
  ({ phase: "focus", from: now, until: now + plan.focusMin * MIN, round });

/** How much of the phase has gone, 0 to 1. */
export function pomodoroDone(p: Pomodoro, now: number): number {
  const length = p.until - p.from;
  return length > 0 ? Math.min(1, Math.max(0, (now - p.from) / length)) : 1;
}

/**
 * The timer at [now], and the bubble that phase change asks for. A focus that ended turns into the rest; a rest that
 * ended starts the next focus (auto) or stops the timer and asks whether to go again. A timer found after the next
 * phase would have ended too (the app was closed) stops without asking.
 */
export function stepPomodoro(
  p: Pomodoro | null, now: number, plan: PomodoroPlan,
): { pomodoro: Pomodoro | null; bubble: PomodoroBubble | null } {
  if (!p || now < p.until) return { pomodoro: p, bubble: null };
  const quiet = { pomodoro: null, bubble: null };
  if (p.phase === "focus") {
    const long = plan.long && p.round % LONG_EVERY === 0;
    const until = p.until + restMs(plan, long);
    return now < until ? { pomodoro: { phase: "rest", from: p.until, until, round: p.round, long }, bubble: "rest" } : quiet;
  }
  if (plan.auto) {
    const next = startPomodoro(p.until, plan, p.round + 1);
    return now < next.until ? { pomodoro: next, bubble: "back" } : quiet;
  }
  return now < p.until + restMs(plan, false) ? { pomodoro: null, bubble: "again" } : quiet;
}

/** Time left as m:ss. */
export function clockText(ms: number): string {
  const sec = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

/** A stored timer, or null for anything that is not one. A missing round counts as the first, a missing start as the end. */
export function readPomodoro(raw: unknown): Pomodoro | null {
  const p = raw as Partial<Pomodoro> | null;
  if (!p || typeof p !== "object" || (p.phase !== "focus" && p.phase !== "rest")) return null;
  if (typeof p.until !== "number" || !Number.isFinite(p.until)) return null;
  const from = typeof p.from === "number" && Number.isFinite(p.from) && p.from <= p.until ? p.from : p.until;
  const round = Number.isInteger(p.round) && (p.round as number) > 0 ? (p.round as number) : 1;
  return p.phase === "rest"
    ? { phase: "rest", from, until: p.until, round, long: p.long === true }
    : { phase: "focus", from, until: p.until, round };
}
