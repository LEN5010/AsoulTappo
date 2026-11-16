// The own pet's todos: a short list kept on this device, each with an optional reminder time that repeats or not.
// Pure: the caller (stores/todo.ts) steps the list with the clock and shows what comes due over the own pet.
//
// - A reminder time rings once. `rang` keeps the time it rang for, so a clock set back does not ring it again, and
//   one that passed while the app was closed, the computer slept or the clock was set forward rings on the next step,
//   counted as late.
// - A repeating todo keeps its time until it is ticked off; ticking it off moves it to the next time after now.
// - Ticked-off todos stay for KEEP_DONE_MS, then go.

export type TodoRepeat = "none" | "daily" | "weekdays" | "weekly";
export const REPEATS: readonly TodoRepeat[] = ["none", "daily", "weekdays", "weekly"];
export const REPEAT_LABEL: Record<TodoRepeat, string> = { none: "不重复", daily: "每天", weekdays: "工作日", weekly: "每周" };

export interface Todo {
  id: string;
  title: string;
  /** Reminder time in ms since the epoch; null for none. */
  at: number | null;
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
/** The quick times: tonight's and tomorrow morning's hour; before EARLY_HOUR, tomorrow morning is this morning. */
export const TONIGHT_HOUR = 20;
export const MORNING_HOUR = 9;
export const EARLY_HOUR = 5;

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

export function newTodo(id: string, title: string, at: number | null, repeat: TodoRepeat, now: number): Todo {
  const time = at == null ? null : Math.floor(at / MIN) * MIN;
  const rep = time == null ? "none" : repeat;
  return {
    id, title: cleanTitle(title), at: time == null ? null : firstTime(time, rep), repeat: rep,
    snooze: null, rang: null, doneAt: null, created: now,
  };
}

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

/** Open and past its time. */
export const isOverdue = (t: Todo, now: number) => t.doneAt == null && t.at != null && t.at <= now;

/** Open ones by time (untimed last, then by when they were added), ticked-off ones after them, latest first. */
export function sortTodos(list: readonly Todo[]): Todo[] {
  return [...list].sort((a, b) => {
    if ((a.doneAt == null) !== (b.doneAt == null)) return a.doneAt == null ? -1 : 1;
    if (a.doneAt != null && b.doneAt != null) return b.doneAt - a.doneAt;
    if ((a.at == null) !== (b.at == null)) return a.at == null ? 1 : -1;
    return (a.at ?? 0) - (b.at ?? 0) || a.created - b.created;
  });
}

/** Today's view: timed todos due by the end of today, open or ticked off today. */
export function todayTodos(list: readonly Todo[], now: number): Todo[] {
  const start = dayStart(now);
  const end = dayEnd(now);
  return sortTodos(list.filter((t) => t.at != null && t.at < end && (t.doneAt == null || t.doneAt >= start)));
}

/** The quick times offered at [now]; tonight's is left out once it has passed. */
export function quickTimes(now: number): { key: "hour" | "tonight" | "morning"; label: string; at: number }[] {
  const hour = Math.floor((now + 60 * MIN) / MIN) * MIN;
  const d = new Date(now);
  const tonight = new Date(now);
  tonight.setHours(TONIGHT_HOUR, 0, 0, 0);
  const morning = new Date(now);
  if (d.getHours() >= EARLY_HOUR) morning.setDate(morning.getDate() + 1);
  morning.setHours(MORNING_HOUR, 0, 0, 0);
  const out: { key: "hour" | "tonight" | "morning"; label: string; at: number }[] = [{ key: "hour", label: "一小时后", at: hour }];
  if (tonight.getTime() > now) out.push({ key: "tonight", label: `今晚 ${TONIGHT_HOUR - 12} 点`, at: tonight.getTime() });
  out.push({ key: "morning", label: `明早 ${MORNING_HOUR} 点`, at: morning.getTime() });
  return out;
}

/** Whole days from the day of [now] to the day of [t] (negative before it). */
export function dayOffset(t: number, now: number): number {
  return Math.round((dayStart(t) - dayStart(now)) / DAY);
}

/** The day of [t] as seen at [now]: 今天, 明天, 昨天 or the date. */
export function dayText(t: number, now: number): string {
  const off = dayOffset(t, now);
  if (off === 0) return "今天";
  if (off === 1) return "明天";
  if (off === -1) return "昨天";
  const d = new Date(t);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

/** The custom time's date strip: today and the next [days] - 1 days, named 今天, 明天, 后天, then by weekday. */
export function dayStrip(now: number, days = 7): { off: number; label: string; date: number }[] {
  return Array.from({ length: days }, (_, off) => {
    const d = new Date(now);
    d.setDate(d.getDate() + off);
    return { off, label: off < 3 ? ["今天", "明天", "后天"][off] : WEEKDAYS[d.getDay()], date: d.getDate() };
  });
}

/** Ticked-off todos, latest first. */
export const doneTodos = (list: readonly Todo[]) =>
  list.filter((t) => t.doneAt != null).sort((a, b) => b.doneAt! - a.doneAt!);

const pad = (n: number) => String(n).padStart(2, "0");
export const clockOf = (t: number) => { const d = new Date(t); return `${d.getHours()}:${pad(d.getMinutes())}`; };

/** A todo's time in the list: the clock alone for today, with the day otherwise. */
export function whenText(t: number, now: number): string {
  return dayOffset(t, now) === 0 ? clockOf(t) : `${dayText(t, now)} ${clockOf(t)}`;
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
      id: t.id, title, at, repeat, snooze: num(t.snooze), rang: num(t.rang), doneAt: num(t.doneAt),
      created: num(t.created) ?? 0,
    });
    if (out.length >= MAX_TODOS) break;
  }
  return out;
}
