// Local tap counters for the counter bar under the pet (today / all time).
// Purely local and instant; the server keeps its own rate-limited total for progression.
import { reactive } from "vue";

const KEY = "asoultappo.counter.v1";

export function dayKey(d = new Date()): string {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function load(): { day: string; today: number; total: number } {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (v && typeof v.today === "number" && typeof v.total === "number" && typeof v.day === "string") return v;
  } catch {
    /* corrupt or unavailable */
  }
  return { day: dayKey(), today: 0, total: 0 };
}

export const counter = reactive(load());

let saveTimer: ReturnType<typeof setTimeout> | undefined;

export function bumpCounter(n = 1, now = new Date()): void {
  const day = dayKey(now);
  if (counter.day !== day) {
    counter.day = day;
    counter.today = 0;
  }
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
