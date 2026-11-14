// When the own pet reminds the player to drink water, to get up, and asks about lunch. Pure timing: the caller ticks
// it with the clock, reports input, and shows what `due` returns once nothing else holds the spot over the pet.
//
// - Water: after 90 to 150 minutes of use, counted only while the player is at the computer.
// - Sitting: after 60 minutes of use without a break of 5 minutes or more; a break starts the count again.
// - Lunch: once a day, at a random minute from 11:30 to 13:00, the first time the player is at the computer from
//   then until 13:30.
// Two reminders keep at least 10 minutes apart; one that comes due meanwhile waits.

export type NudgeKind = "water" | "move" | "lunch";

const MIN = 60_000;
/** No input for this long and the player is away: nothing is counted or shown, and sitting starts over. */
export const AWAY_MS = 5 * MIN;
export const WATER_MS: [number, number] = [90 * MIN, 150 * MIN];
export const MOVE_MS = 60 * MIN;
export const SPACING_MS = 10 * MIN;
/** Lunch window as minutes after midnight: asked from a random minute in [from, until), skipped after `last`. */
export const LUNCH = { from: 11 * 60 + 30, until: 13 * 60, last: 13 * 60 + 30 };

export const LINES: Record<Exclude<NudgeKind, "lunch">, string[]> = {
  water: ["该喝水啦，去接一杯吧", "喝口水歇一下吧", "好一阵没喝水了哦", "杯子空了吗？续一杯吧", "记得喝水哦"],
  move: ["坐了快一小时啦，起来走走", "站起来伸个懒腰吧", "该起来活动活动啦", "转转肩膀和脖子吧", "看看远处，歇歇眼睛吧"],
};
export const LUNCH_ASK = "午饭吃了没？";
export const LUNCH_REPLY = {
  ate: ["好耶，下午也要加油", "吃饱了才有力气"],
  notYet: ["快去吃饭吧，别饿着", "先去吃饭，回来再继续"],
};

export const pick = <T>(list: readonly T[], rand: () => number): T => list[Math.min(list.length - 1, Math.floor(rand() * list.length))];

const minuteOfDay = (t: number) => { const d = new Date(t); return d.getHours() * 60 + d.getMinutes(); };
const dayOf = (t: number) => { const d = new Date(t); return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`; };

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

  constructor(now: number, private rand: () => number = Math.random, lunchDay = "") {
    this.lastTick = now;
    this.waterAt = this.nextWater();
    this.lunchDay = lunchDay;
    this.lunchMinute = LUNCH.from;
  }

  private nextWater() {
    const [lo, hi] = WATER_MS;
    return lo + this.rand() * (hi - lo);
  }

  private away(now: number) {
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
    if (this.lunchDay !== day && minute >= this.lunchMinute && minute < LUNCH.last) return "lunch";
    if (this.sitSince != null && now - this.sitSince >= MOVE_MS) return "move";
    if (this.water >= this.waterAt) return "water";
    return null;
  }

  /** The reminder went up. Getting up for one counts for the others: a stretch break also resets water's count. */
  shown(kind: NudgeKind, now: number) {
    this.lastShown = now;
    if (kind === "lunch") this.lunchDay = dayOf(now);
    if (kind === "move") this.sitSince = now;
    if (kind === "water" || kind === "move") {
      this.water = 0;
      this.waterAt = this.nextWater();
    }
  }

  /** The day lunch was last asked, for keeping across restarts. */
  get askedLunch() {
    return this.lunchDay;
  }
}
