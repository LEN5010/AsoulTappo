// When the own pet reminds the player of something for their health, asks about lunch, says hello and says to go to
// bed. Pure timing: the caller ticks it with the clock, reports input, and shows what `due` returns once nothing else
// holds the spot over the pet.
//
// - Hello: the first time the player is at the computer each day from 5:00, worded for the time of day.
// - Bed: once a night, the first time the player is at the computer from 0:30 until 5:00.
// - Lunch: once a day, at a random minute from 11:30 to 13:00, the first time the player is at the computer from
//   then until 13:30.
// - The player's reminders (reminders.ts: water, getting up and so on): each after its own minutes of use, counted
//   only while the player is at the computer and a little uneven, so they do not come like clockwork. The ones a
//   break answers start over after a break of 5 minutes or more.
// Two reminders keep at least 10 minutes apart; one that comes due meanwhile waits, the most overdue first.
import { REST_ANSWERS, type Reminder } from "./reminders";

export type NudgeKind = "tip" | "lunch" | "greet" | "night";
/** A reminder that is due: for `tip`, which of the player's. */
export interface Due { kind: NudgeKind; tip?: Reminder }
/** The days the once-a-day reminders were last shown, kept across restarts. */
export interface NudgeDays { lunch?: string; greet?: string; night?: string }
/** Which of the once-a-day reminders the player keeps on. */
export interface DailyOn { lunch: boolean; greet: boolean; night: boolean }

const MIN = 60_000;
/** No input for this long and the player is away: nothing is counted or shown, and sitting starts over. */
export const AWAY_MS = 5 * MIN;
export const SPACING_MS = 10 * MIN;
/** A reminder comes after its minutes times a factor from this range. */
export const UNEVEN: [number, number] = [0.85, 1.15];
/** Lunch window as minutes after midnight: asked from a random minute in [from, until), skipped after `last`. */
export const LUNCH = { from: 11 * 60 + 30, until: 13 * 60, last: 13 * 60 + 30 };
/** Hellos from this minute of the day on; the night before it is the bedtime window's. */
export const GREET_FROM = 5 * 60;
/** The bedtime reminder's window, as minutes after midnight. */
export const NIGHT = { from: 30, until: 5 * 60 };

/** Hellos by the minute of the day each wording starts from, latest last. */
export const GREETS: [number, string[]][] = [
  [GREET_FROM, ["早上好，今天也加油", "早呀，新的一天开始啦"]],
  [11 * 60, ["中午好，忙了一上午吧", "中午好呀"]],
  [13 * 60, ["下午好，继续加油", "下午好呀"]],
  [18 * 60, ["晚上好，今天辛苦啦", "晚上好呀"]],
];
export const NIGHT_LINES = ["很晚啦，早点睡吧", "该睡觉啦，明天见", "熬夜伤身，快去睡吧"];
export const LUNCH_ASK = "午饭吃了没？";
export const LUNCH_REPLY = {
  ate: ["好耶，下午也要加油", "吃饱了才有力气"],
  notYet: ["快去吃饭吧，别饿着", "先去吃饭，回来再继续"],
};

export const pick = <T>(list: readonly T[], rand: () => number): T => list[Math.min(list.length - 1, Math.floor(rand() * list.length))];

export const minuteOfDay = (t: number) => { const d = new Date(t); return d.getHours() * 60 + d.getMinutes(); };
export const dayOf = (t: number) => { const d = new Date(t); return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`; };

/** The hello for [minute] of the day. */
export function greetLine(minute: number, rand: () => number): string {
  let lines = GREETS[0][1];
  for (const [from, words] of GREETS) if (minute >= from) lines = words;
  return pick(lines, rand);
}

/** How far one reminder has counted: time at the computer since it last came up, and the amount that brings it. */
interface Count { used: number; every: number; at: number }

export class NudgeClock {
  private lastInput = -Infinity;
  private lastTick: number;
  private counts = new Map<string, Count>();
  private lastShown = -Infinity;
  /** The day lunch was asked or given up on, and today's minute to ask from. */
  private lunchDay: string;
  private lunchMinute: number;
  private lunchFor = "";
  /** The days the hello and the bedtime reminder were last shown. */
  private greetDay: string;
  private nightDay: string;

  /** [tips]: the player's reminders as they are now, asked at every tick. [daily]: the once-a-day ones kept on. */
  constructor(
    now: number, private rand: () => number = Math.random, days: NudgeDays = {},
    private tips: () => readonly Reminder[] = () => [],
    private daily: () => DailyOn = () => ({ lunch: true, greet: true, night: true }),
  ) {
    this.lastTick = now;
    this.lunchDay = days.lunch ?? "";
    this.greetDay = days.greet ?? "";
    this.nightDay = days.night ?? "";
    this.lunchMinute = LUNCH.from;
  }

  private arm(count: Count, everyMin: number) {
    const [lo, hi] = UNEVEN;
    count.every = everyMin;
    count.at = everyMin * MIN * (lo + this.rand() * (hi - lo));
  }

  /** No input for AWAY_MS: the player is away from the computer (also before the first input). */
  away(now: number) {
    return now - this.lastInput >= AWAY_MS;
  }

  /** A key, a button or the mouse. Coming back from a break starts the reminders a break answers over. */
  input(now: number) {
    if (this.away(now)) this.rested();
    this.lastInput = now;
  }

  /** The player took a break (away from the computer, or a rest of the tomato timer). */
  rested() {
    for (const [id, count] of this.counts) if (REST_ANSWERS.has(id)) count.used = 0;
  }

  /**
   * Advances the counts to `now` and answers the reminder due, if any; nothing is marked shown until `shown` is
   * called, so a reminder held back by something else on screen stays due.
   */
  due(now: number): Due | null {
    const step = Math.max(0, now - this.lastTick);
    this.lastTick = now;
    if (this.away(now)) return null;
    const tips = this.tips().filter((tip) => tip.on);
    for (const id of [...this.counts.keys()]) if (!tips.some((tip) => tip.id === id)) this.counts.delete(id);
    for (const tip of tips) {
      let count = this.counts.get(tip.id);
      if (!count) this.counts.set(tip.id, (count = { used: 0, every: 0, at: 0 }));
      if (count.every !== tip.everyMin) this.arm(count, tip.everyMin);
      // Only the part of the step after the last input counts as away; the rest is time at the computer.
      count.used += Math.min(step, AWAY_MS);
    }
    if (now - this.lastShown < SPACING_MS) return null;
    const day = dayOf(now);
    if (day !== this.lunchFor) {
      this.lunchFor = day;
      this.lunchMinute = LUNCH.from + Math.floor(this.rand() * (LUNCH.until - LUNCH.from));
    }
    const minute = minuteOfDay(now);
    const daily = this.daily();
    if (daily.night && this.nightDay !== day && minute >= NIGHT.from && minute < NIGHT.until) return { kind: "night" };
    if (daily.greet && this.greetDay !== day && minute >= GREET_FROM) return { kind: "greet" };
    if (daily.lunch && this.lunchDay !== day && minute >= this.lunchMinute && minute < LUNCH.last) return { kind: "lunch" };
    let tip: Reminder | undefined;
    let most = 1;
    for (const t of tips) {
      const count = this.counts.get(t.id)!;
      const over = count.used / count.at;
      if (over >= most) [tip, most] = [t, over];
    }
    return tip ? { kind: "tip", tip } : null;
  }

  /** The reminder went up. */
  shown(due: Due, now: number) {
    this.lastShown = now;
    if (due.kind === "lunch") this.lunchDay = dayOf(now);
    if (due.kind === "greet") this.greetDay = dayOf(now);
    if (due.kind === "night") this.nightDay = dayOf(now);
    const count = due.tip && this.counts.get(due.tip.id);
    if (count) {
      count.used = 0;
      this.arm(count, due.tip!.everyMin);
    }
  }

  /** Something else went up over the pet: the next reminder keeps its distance from it too. */
  mark(now: number) {
    this.lastShown = now;
  }

  /** The days of the once-a-day reminders, for keeping across restarts. */
  get days(): Required<NudgeDays> {
    return { lunch: this.lunchDay, greet: this.greetDay, night: this.nightDay };
  }
}
