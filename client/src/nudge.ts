// When the own pet reminds the player to drink water, to get up, asks about lunch, says hello and says to go to bed.
// Pure timing: the caller ticks it with the clock, reports input, and shows what `due` returns once nothing else holds
// the spot over the pet.
//
// - Hello: the first time the player is at the computer each day from 5:00, worded for the time of day.
// - Bed: once a night, the first time the player is at the computer from 0:30 until 5:00.
// - Water: after 90 to 150 minutes of use, counted only while the player is at the computer.
// - Sitting: after 60 minutes of use without a break of 5 minutes or more; a break starts the count again.
// - Lunch: once a day, at a random minute from 11:30 to 13:00, the first time the player is at the computer from
//   then until 13:30.
// Two reminders keep at least 10 minutes apart; one that comes due meanwhile waits.

export type NudgeKind = "water" | "move" | "lunch" | "greet" | "night";
/** The days the once-a-day reminders were last shown, kept across restarts. */
export interface NudgeDays { lunch?: string; greet?: string; night?: string }

const MIN = 60_000;
/** No input for this long and the player is away: nothing is counted or shown, and sitting starts over. */
export const AWAY_MS = 5 * MIN;
export const WATER_MS: [number, number] = [90 * MIN, 150 * MIN];
export const MOVE_MS = 60 * MIN;
export const SPACING_MS = 10 * MIN;
/** Lunch window as minutes after midnight: asked from a random minute in [from, until), skipped after `last`. */
export const LUNCH = { from: 11 * 60 + 30, until: 13 * 60, last: 13 * 60 + 30 };
/** Hellos from this minute of the day on; the night before it is the bedtime window's. */
export const GREET_FROM = 5 * 60;
/** The bedtime reminder's window, as minutes after midnight. */
export const NIGHT = { from: 30, until: 5 * 60 };

export const LINES: Record<"water" | "move", string[]> = {
  water: ["该喝水啦，去接一杯吧", "喝口水歇一下吧", "好一阵没喝水了哦", "杯子空了吗？续一杯吧", "记得喝水哦"],
  move: ["坐了快一小时啦，起来走走", "站起来伸个懒腰吧", "该起来活动活动啦", "转转肩膀和脖子吧", "看看远处，歇歇眼睛吧"],
};
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

export class NudgeClock {
  private lastInput = -Infinity;
  private lastTick: number;
  /** Time at the computer since the last water reminder, and the amount that brings the next one. */
  private water = 0;
  private waterAt: number;
  /** Start of the current stretch without a break. */
  private sitSince: number | null = null;
  private lastShown = -Infinity;
  /** The day lunch was asked or given up on, and today's minute to ask from. */
  private lunchDay: string;
  private lunchMinute: number;
  private lunchFor = "";
  /** The days the hello and the bedtime reminder were last shown. */
  private greetDay: string;
  private nightDay: string;

  constructor(now: number, private rand: () => number = Math.random, days: NudgeDays = {}) {
    this.lastTick = now;
    this.waterAt = this.nextWater();
    this.lunchDay = days.lunch ?? "";
    this.greetDay = days.greet ?? "";
    this.nightDay = days.night ?? "";
    this.lunchMinute = LUNCH.from;
  }

  private nextWater() {
    const [lo, hi] = WATER_MS;
    return lo + this.rand() * (hi - lo);
  }

  /** No input for AWAY_MS: the player is away from the computer (also before the first input). */
  away(now: number) {
    return now - this.lastInput >= AWAY_MS;
  }

  /** A key, a button or the mouse. */
  input(now: number) {
    if (this.away(now)) this.sitSince = now;
    this.lastInput = now;
  }

  /**
   * Advances the counts to `now` and answers the reminder due, if any; nothing is marked shown until `shown` is
   * called, so a reminder held back by something else on screen stays due.
   */
  due(now: number): NudgeKind | null {
    const step = Math.max(0, now - this.lastTick);
    this.lastTick = now;
    if (this.away(now)) {
      this.sitSince = null;
      return null;
    }
    // Only the part of the step after the last input counts as away; the rest is time at the computer.
    this.water += Math.min(step, AWAY_MS);
    if (now - this.lastShown < SPACING_MS) return null;
    const day = dayOf(now);
    if (day !== this.lunchFor) {
      this.lunchFor = day;
      this.lunchMinute = LUNCH.from + Math.floor(this.rand() * (LUNCH.until - LUNCH.from));
    }
    const minute = minuteOfDay(now);
    if (this.nightDay !== day && minute >= NIGHT.from && minute < NIGHT.until) return "night";
    if (this.greetDay !== day && minute >= GREET_FROM) return "greet";
    if (this.lunchDay !== day && minute >= this.lunchMinute && minute < LUNCH.last) return "lunch";
    if (this.sitSince != null && now - this.sitSince >= MOVE_MS) return "move";
    if (this.water >= this.waterAt) return "water";
    return null;
  }

  /** The reminder went up. Getting up for one counts for the others: a stretch break also resets water's count. */
  shown(kind: NudgeKind, now: number) {
    this.lastShown = now;
    if (kind === "lunch") this.lunchDay = dayOf(now);
    if (kind === "greet") this.greetDay = dayOf(now);
    if (kind === "night") this.nightDay = dayOf(now);
    if (kind === "move") this.sitSince = now;
    if (kind === "water" || kind === "move") {
      this.water = 0;
      this.waterAt = this.nextWater();
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
