// Local tap counters for the counter bar under the pet (today / all time).
// Purely local and instant; the server keeps its own rate-limited total for progression.
import { reactive } from "vue";

const KEY = "asoultappo.counter.v1";

export function dayKey(d = new Date()): string {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

/** The stored counters; a count saved on an earlier day starts today at 0. */
export function load(now = new Date(), storage?: Pick<Storage, "getItem">): { day: string; today: number; total: number } {
  const day = dayKey(now);
  try {
    // localStorage is read inside the try: where storage is blocked, reaching for it throws.
    const v = JSON.parse((storage ?? localStorage).getItem(KEY) ?? "null");
    if (v && typeof v.today === "number" && typeof v.total === "number" && typeof v.day === "string") {
      return v.day === day ? v : { day, today: 0, total: v.total };
    }
  } catch {
    /* corrupt or unavailable */
  }
  return { day, today: 0, total: 0 };
}

export const counter = reactive(load());

/** Starts a new day's count once the date has changed. */
export function rollDay(now = new Date()): void {
  const day = dayKey(now);
  if (counter.day !== day) {
    counter.day = day;
    counter.today = 0;
  }
}

/** Rolls the day over while no keys are pressed; a check a minute is enough for a day counter. */
export function watchDay(everyMs = 60000): () => void {
  const timer = setInterval(() => rollDay(), everyMs);
  return () => clearInterval(timer);
}

let saveTimer: ReturnType<typeof setTimeout> | undefined;

export function bumpCounter(n = 1, now = new Date()): void {
  rollDay(now);
  counter.today += n;
  counter.total += n;
  if (saveTimer) return;
  saveTimer = setTimeout(() => {
    saveTimer = undefined;
    try {
      localStorage.setItem(KEY, JSON.stringify(counter));
    } catch {
      /* storage unavailable */
    }
  }, 2000);
}
