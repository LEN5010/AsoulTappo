// The own pet's todos: a short list kept on this device, each with an optional reminder time that repeats or not.
// Pure: the caller (stores/todo.ts) steps the list with the clock and shows what comes due over the own pet.
//
// - A reminder time rings once. `rang` keeps the time it rang for, so a clock set back does not ring it again, and
//   one that passed while the app was closed, the computer slept or the clock was set forward rings on the next step,
//   counted as late.
// - A repeating todo keeps its time until it is ticked off; ticking it off moves it to the next time after now.
// - Ticked-off todos stay for KEEP_DONE_MS, then go.
// - An all-day todo has a day and no time of day: `at` is that day at MORNING_HOUR, when it rings. Set for today after
//   that hour it starts as rung; it is overdue only once its day is over.

export type TodoRepeat = "none" | "daily" | "weekdays" | "weekly";
export const REPEATS: readonly TodoRepeat[] = ["none", "daily", "weekdays", "weekly"];
export const REPEAT_LABEL: Record<TodoRepeat, string> = { none: "不重复", daily: "每天", weekdays: "工作日", weekly: "每周" };

export interface Todo {
  id: string;
  title: string;
  /** Reminder time in ms since the epoch; null for none. */
  at: number | null;
  /** A day without a time of day: `at` is that day at MORNING_HOUR. Absent in lists stored before 1.2.4 (timed). */
  allDay: boolean;
  /** Always "none" without a time. */
  repeat: TodoRepeat;
  /** Reminded again at this time (the bubble's later key); kept after it rings. */
  snooze: number | null;
  /** The reminder time the last ring was for. */
  rang: number | null;
  /** When it was ticked off; null while open. */
  doneAt: number | null;
  created: number;
}

const MIN = 60_000;
const DAY = 24 * 60 * MIN;
export const TITLE_MAX = 40;
export const MAX_TODOS = 200;
export const SNOOZE_MS = 10 * MIN;
/** A reminder found later than this after its time passed while the app was not watching: it is late. */
export const LATE_MS = 2 * MIN;
export const KEEP_DONE_MS = 7 * DAY;
/** An all-day todo rings at this hour of its day. */
export const MORNING_HOUR = 9;
/** The quick hours of the time picker. */
export const QUICK_HOURS = [9, 12, 18, 20] as const;

export const DONE_LINES = ["做完啦", "好耶，又完成一件", "干得漂亮"];

export const cleanTitle = (text: string) => [...text.trim().replace(/\s+/g, " ")].slice(0, TITLE_MAX).join("");

/** When the todo reminds next, whether or not that already rang. */
export const remindAt = (t: Todo) => (t.doneAt == null ? t.snooze ?? t.at : null);

const isWeekend = (d: Date) => d.getDay() === 0 || d.getDay() === 6;

/** Local midnight that starts the day of [t]. */
export function dayStart(t: number): number {
  const d = new Date(t);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}
/** Local midnight that ends the day of [t]. */
export function dayEnd(t: number): number {
  const d = new Date(t);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 1);
  return d.getTime();
}

/** The first time of a new todo: a working-days todo set on a weekend starts on the Monday. */
export function firstTime(at: number, repeat: TodoRepeat): number {
  if (repeat !== "weekdays") return at;
  const d = new Date(at);
  const h = d.getHours();
  const m = d.getMinutes();
  while (isWeekend(d)) {
    d.setDate(d.getDate() + 1);
    d.setHours(h, m, 0, 0);
  }
  return d.getTime();
}

/**
 * The first time of the series through [at] that comes after [after]. Steps by calendar days in local time, so the
 * time of day holds across midnight, month ends and daylight saving.
 */
export function nextTime(at: number, repeat: TodoRepeat, after: number): number {
  if (repeat === "none") return at;
  const d = new Date(at);
  const h = d.getHours();
  const m = d.getMinutes();
  // Far behind: whole weeks first; a week on from a time of the series is one too.
  const weeks = Math.floor((after - at) / (7 * DAY)) - 1;
  if (weeks > 0) d.setDate(d.getDate() + weeks * 7);
  do {
    d.setDate(d.getDate() + (repeat === "weekly" ? 7 : 1));
    if (repeat === "weekdays") while (isWeekend(d)) d.setDate(d.getDate() + 1);
    d.setHours(h, m, 0, 0);
  } while (d.getTime() <= after);
  return d.getTime();
}

/** When a todo reminds: a time, or a day (`allDay`, any time of that day), and how it repeats. */
export interface TodoWhen { at: number | null; allDay: boolean; repeat: TodoRepeat }
export const NO_WHEN: TodoWhen = { at: null, allDay: false, repeat: "none" };

/** [when] as kept: seconds dropped, an all-day time moved to MORNING_HOUR, the first time of a working-days series. */
function placeWhen(when: TodoWhen, now: number): Pick<Todo, "at" | "allDay" | "repeat" | "rang" | "snooze"> {
  if (when.at == null) return { at: null, allDay: false, repeat: "none", rang: null, snooze: null };
  let time = Math.floor(when.at / MIN) * MIN;
  if (when.allDay) {
    const d = new Date(time);
    d.setHours(MORNING_HOUR, 0, 0, 0);
    time = d.getTime();
  }
  const at = firstTime(time, when.repeat);
  // A day set after its morning hour has passed does not ring that day.
  return { at, allDay: when.allDay, repeat: when.repeat, rang: when.allDay && at <= now ? at : null, snooze: null };
}

export function newTodo(id: string, title: string, when: TodoWhen, now: number): Todo {
  return { id, title: cleanTitle(title), ...placeWhen(when, now), doneAt: null, created: now };
}

/** A new title: kept unless it is empty once cleaned. */
export function renameTodo(t: Todo, title: string): Todo {
  const name = cleanTitle(title);
  return name && name !== t.title ? { ...t, title: name } : t;
}

/** A new time, day or repeat (or none): it rings afresh by the new one. */
export const retimeTodo = (t: Todo, when: TodoWhen, now: number): Todo => ({ ...t, ...placeWhen(when, now) });

export const whenOf = (t: Todo): TodoWhen => ({ at: t.at, allDay: t.at != null && t.allDay, repeat: t.repeat });

/** Ticked off: a repeating todo moves to its next time after now (or after its own time, ticked off early). */
export function completeTodo(t: Todo, now: number): Todo {
  if (t.doneAt != null) return t;
  if (t.repeat === "none" || t.at == null) return { ...t, doneAt: now, snooze: null };
  return { ...t, at: nextTime(t.at, t.repeat, Math.max(now, t.at)), snooze: null, rang: null };
}

export const reopenTodo = (t: Todo): Todo => (t.doneAt == null ? t : { ...t, doneAt: null });

export const snoozeTodo = (t: Todo, now: number): Todo =>
  (t.doneAt == null ? { ...t, snooze: Math.floor((now + SNOOZE_MS) / 1000) * 1000 } : t);

export interface TodoStep {
  /** The same array when nothing changed. */
  list: Todo[];
  /** Rang within LATE_MS of their time. */
  onTime: Todo[];
  /** Rang later than that: their time passed while nothing was watching. */
  late: Todo[];
}

/** The list at [now]: what comes due rings (and is marked so), ticked-off todos past keeping go. */
export function stepTodos(list: Todo[], now: number): TodoStep {
  const onTime: Todo[] = [];
  const late: Todo[] = [];
  let changed = false;
  const out: Todo[] = [];
  for (const t of list) {
    if (t.doneAt != null && now - t.doneAt > KEEP_DONE_MS) {
      changed = true;
      continue;
    }
    const r = remindAt(t);
    if (r == null || r > now || t.rang === r) {
      out.push(t);
      continue;
    }
    const rung = { ...t, rang: r };
    out.push(rung);
    (now - r <= LATE_MS ? onTime : late).push(rung);
    changed = true;
  }
  return { list: changed ? out : list, onTime, late };
}

/** Open and past its time; an all-day one once its day is over. */
export const isOverdue = (t: Todo, now: number) =>
  t.doneAt == null && t.at != null && (t.allDay ? dayEnd(t.at) <= now : t.at <= now);

/**
 * The list as shown at [now]: overdue first, then by time (an all-day one at the start of its day, before the timed
 * ones of that day), untimed after them by when they were added; ticked-off ones last, latest first.
 */
export function sortTodos(list: readonly Todo[], now: number): Todo[] {
  const key = (t: Todo) => (t.at == null ? Infinity : t.allDay ? dayStart(t.at) : t.at);
  return [...list].sort((a, b) => {
    if ((a.doneAt == null) !== (b.doneAt == null)) return a.doneAt == null ? -1 : 1;
    if (a.doneAt != null && b.doneAt != null) return b.doneAt - a.doneAt;
    const late = Number(isOverdue(b, now)) - Number(isOverdue(a, now));
    if (late) return late;
    return key(a) - key(b) || (a.allDay === b.allDay ? 0 : a.allDay ? -1 : 1) || a.created - b.created;
  });
}

/** The quick hours of the time picker on the day of [day]: each one's time, and whether it has passed at [now]. */
export function quickHours(day: number, now: number): { hour: number; at: number; past: boolean }[] {
  return QUICK_HOURS.map((hour) => {
    const at = timeAt(day, 0, hour, 0);
    return { hour, at, past: at <= now };
  });
}

/** An hour from [now], to the minute. */
export const hourOn = (now: number) => Math.floor((now + 60 * MIN) / MIN) * MIN;

/** Whole days from the day of [now] to the day of [t] (negative before it). */
export function dayOffset(t: number, now: number): number {
  return Math.round((dayStart(t) - dayStart(now)) / DAY);
}

export const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
/** Days of the strip, today included; the days after them are named by their date. */
export const STRIP_DAYS = 7;

/** The day of [t] as seen at [now]: 今天, 明天, 昨天, the weekday within the strip's week, else the date. */
export function dayText(t: number, now: number): string {
  const off = dayOffset(t, now);
  if (off === 0) return "今天";
  if (off === 1) return "明天";
  if (off === -1) return "昨天";
  const d = new Date(t);
  if (off > 1 && off < STRIP_DAYS) return WEEKDAYS[d.getDay()];
  const date = `${d.getMonth() + 1}月${d.getDate()}日`;
  return d.getFullYear() === new Date(now).getFullYear() ? date : `${d.getFullYear()}年${date}`;
}

/** The time picker's date strip: today and the next [days] - 1 days, named 今天, 明天, then by weekday. */
export function dayStrip(now: number, days = STRIP_DAYS): { off: number; label: string; date: number; at: number }[] {
  return Array.from({ length: days }, (_, off) => {
    const d = new Date(now);
    d.setDate(d.getDate() + off);
    d.setHours(0, 0, 0, 0);
    return { off, label: off < 2 ? ["今天", "明天"][off] : WEEKDAYS[d.getDay()], date: d.getDate(), at: d.getTime() };
  });
}

/**
 * The month of [month] (any time in it) as calendar weeks from Monday: each cell the local midnight of its day,
 * null before the first and after the last.
 */
export function monthWeeks(month: number): (number | null)[][] {
  const first = new Date(month);
  first.setDate(1);
  first.setHours(0, 0, 0, 0);
  const lead = (first.getDay() + 6) % 7;
  const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const cells: (number | null)[] = Array.from({ length: lead }, () => null);
  for (let day = 1; day <= days; day++) cells.push(new Date(first.getFullYear(), first.getMonth(), day).getTime());
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

/** Ticked-off todos, latest first. */
export const doneTodos = (list: readonly Todo[]) =>
  list.filter((t) => t.doneAt != null).sort((a, b) => b.doneAt! - a.doneAt!);

const pad = (n: number) => String(n).padStart(2, "0");
export const clockOf = (t: number) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

/** A todo's time as written in the list and on the time key: 今天, 明天 20:00, 周五 09:00. */
export function whenText(t: number, allDay: boolean, now: number): string {
  return allDay ? dayText(t, now) : `${dayText(t, now)} ${clockOf(t)}`;
}

/** The time [days] after today at [hour]:[minute], local. */
export function timeAt(now: number, days: number, hour: number, minute: number): number {
  const d = new Date(now);
  d.setDate(d.getDate() + days);
  d.setHours(hour, minute, 0, 0);
  return d.getTime();
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** A stored list, keeping only well-formed todos. */
export function readTodos(raw: unknown): Todo[] {
  if (!Array.isArray(raw)) return [];
  const out: Todo[] = [];
  const ids = new Set<string>();
  for (const item of raw) {
    const t = item as Partial<Todo> | null;
    if (!t || typeof t !== "object" || typeof t.id !== "string" || !t.id || ids.has(t.id)) continue;
    const title = typeof t.title === "string" ? cleanTitle(t.title) : "";
    if (!title) continue;
    const at = num(t.at);
    const repeat = at != null && REPEATS.includes(t.repeat as TodoRepeat) ? (t.repeat as TodoRepeat) : "none";
    ids.add(t.id);
    out.push({
      id: t.id, title, at, allDay: at != null && t.allDay === true, repeat, snooze: num(t.snooze), rang: num(t.rang),
      doneAt: num(t.doneAt), created: num(t.created) ?? 0,
    });
    if (out.length >= MAX_TODOS) break;
  }
  return out;
}
