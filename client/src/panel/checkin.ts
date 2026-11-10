// Calendar math for the check-in page. Dates are China days as the server writes them (YYYY-MM-DD), so the
// grid follows the server's day whatever time zone this machine is in.
import { manifest } from "../manifest";
import type { CheckinMonth } from "../net/api";

export interface DayCell {
  day: number;
  date: string;
  when: "past" | "today" | "future";
  /** What that day's check-in won; undefined when the player did not check in. */
  won?: { prize: number; shards: number };
}

/** The month of `today`, Monday first. null pads the first and last week. */
export function monthCells(month: CheckinMonth): (DayCell | null)[] {
  const [y, m, today] = month.today.split("-").map(Number) as [number, number, number];
  const lead = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const won = new Map(month.days.map((d) => [d.day, { prize: d.prize, shards: d.shards }]));
  const cells: (DayCell | null)[] = Array.from({ length: lead }, () => null);
  for (let day = 1; day <= length; day++) {
    const date = `${month.today.slice(0, 8)}${String(day).padStart(2, "0")}`;
    cells.push({ day, date, when: day < today ? "past" : day === today ? "today" : "future", won: won.get(date) });
  }
  while (cells.length % 7) cells.push(null);
  return cells;
}

/** A run of blank squares before the 1st or after the last day, with the stickers pasted over it. */
export interface PadRun {
  /** Index of the run's first square in monthCells. */
  at: number;
  span: number;
  stickers: string[];
  /** The run before the 1st: its stickers stand on the top edge of the next row, cut edge down. */
  stand: boolean;
}

/**
 * 阿草's cutouts for the blank squares: none of the faces the calendar already shows (the host and the prizes), no
 * framed pictures (微笑, 谢谢观看) and none with words (才八点, 晚安). Whole figures can sit anywhere; figures cut off flat at
 * the bottom only stand on the row under the first week, where the cut lies along the squares' top edge.
 */
export const WHOLE_STICKERS = ["兜风", "索嗨嗨"];
export const STANDING_STICKERS = ["欢呼", "打call", "安慰", "收到"];

/**
 * The blank runs of a month's grid and which stickers go on each: two on a run of three squares or more, one on a
 * shorter run, three at most in the month. The month picks where each list starts, so each month has its own and a
 * month never changes them.
 */
export function padRuns(cells: readonly (DayCell | null)[], month: number): PadRun[] {
  const first = cells.findIndex((c) => c !== null);
  if (first < 0) return [];
  let last = cells.length - 1;
  while (last > first && cells[last] === null) last--;
  const runs = [
    { at: 0, span: first, stand: true },
    { at: last + 1, span: cells.length - 1 - last, stand: false },
  ].filter((r) => r.span > 0);
  const m = Math.max(1, month) - 1;
  let standing = m % STANDING_STICKERS.length;
  let whole = m % WHOLE_STICKERS.length;
  let left = 3;
  return runs.map((r, n) => {
    const want = Math.min(r.span >= 3 ? 2 : 1, r.stand ? STANDING_STICKERS.length : WHOLE_STICKERS.length);
    // The first run leaves the second at least one.
    const count = Math.min(want, left - (n === 0 && runs.length > 1 ? 1 : 0));
    left -= count;
    const stickers = Array.from({ length: count }, () =>
      r.stand ? STANDING_STICKERS[standing++ % STANDING_STICKERS.length]! : WHOLE_STICKERS[whole++ % WHOLE_STICKERS.length]!);
    return { ...r, stickers };
  });
}

const PRIZES = manifest.economy.checkin.prizes;

/** Draw tone of prize `index`: gold for the top one, wine for the next, coral below. */
export function prizeTone(index: number, count = PRIZES.length): string {
  if (index === count - 1) return "tone-legendary";
  if (index === count - 2) return "tone-epic";
  return "tone-rare";
}

/** 阿草 hates paying out: the bigger the prize, the worse it takes it. Smallest first. Cutouts only, since they
 *  stand big in the head; 微笑 is a framed square picture. */
const REACTIONS = ["比心", "肯定", "观察", "流汗", "生无可恋", "对不起"];

/** 阿草's sticker for prize `index`, spread over the reactions however many prizes there are. */
export function reactionOf(index: number, count = PRIZES.length): string {
  const at = count > 1 ? Math.round((index / (count - 1)) * (REACTIONS.length - 1)) : 0;
  return REACTIONS[Math.min(REACTIONS.length - 1, Math.max(0, at))]!;
}

/** What the sidebar alpaca says when a day turns over. */
export const CHECKIN_LINES = ["小伙伴对不起", "小伙伴你好", "会者不难👋", "难的不会👋", "驼圣帝君也有人黑啊..."];

/** A random line, never the one just said. */
export function pickLine(last = "", rand: () => number = Math.random): string {
  const lines = CHECKIN_LINES.filter((l) => l !== last);
  return lines[Math.floor(rand() * lines.length)] ?? CHECKIN_LINES[0]!;
}
