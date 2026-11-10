// Instant tap counters for the strip, caught up with the server across devices.
// Today follows China Standard Time, the same day boundary as the server.
import { reactive } from "vue";
import type { PlayerStatus } from "../net/api";

const KEY = "asoultappo.counter.v1";
const DAY_ZONE = "Asia/Shanghai";
const DAY_OFFSET_MS = 8 * 60 * 60 * 1000;

export function dayKey(d = new Date()): string {
  return new Date(d.getTime() + DAY_OFFSET_MS).toISOString().slice(0, 10);
}

/** The stored counters; a count saved on an earlier day starts today at 0. */
export function load(now = new Date(), storage?: Pick<Storage, "getItem">): { day: string; today: number; total: number } {
  const day = dayKey(now);
  try {
    // localStorage is read inside the try: where storage is blocked, reaching for it throws.
    const v = JSON.parse((storage ?? localStorage).getItem(KEY) ?? "null");
    if (v && typeof v.today === "number" && typeof v.total === "number" && typeof v.day === "string") {
      // Older clients saved an unpadded local date. In UTC+8 and farther west, its matching local day
      // starts within the China day, so those taps carry over. Lifetime counts carry over everywhere.
      const savedDay = v.day.split("-").map((part: string) => part.padStart(2, "0")).join("-");
      const canKeepToday = v.dayZone === DAY_ZONE || (v.dayZone === undefined && now.getTimezoneOffset() >= -480);
      return { day, today: savedDay === day && canKeepToday ? v.today : 0, total: v.total };
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

function saveSoon(): void {
  if (saveTimer) return;
  saveTimer = setTimeout(() => {
    saveTimer = undefined;
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...counter, dayZone: DAY_ZONE }));
    } catch {
      /* storage unavailable */
    }
  }, 2000);
}

export function bumpCounter(n = 1, now = new Date()): void {
  rollDay(now);
  counter.today += n;
  counter.total += n;
  saveSoon();
}

/**
 * Catches up with the server's counts, which include taps made on the player's other devices.
 * The counts only go up: the local count includes taps beyond the server's activity rate limit.
 * Daily snapshots carry their China date so a response from before midnight stays on its own day.
 */
export function followServer(total: number, daily?: PlayerStatus["dailyTaps"], now = new Date()): void {
  rollDay(now);
  let changed = false;
  if (total > counter.total) {
    counter.total = total;
    changed = true;
  }
  if (daily?.day === counter.day && daily.count > counter.today) {
    counter.today = daily.count;
    changed = true;
  }
  if (changed) saveSoon();
}
