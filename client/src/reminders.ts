// The health reminders a player sets: how often each comes up (minutes at the computer), how long its bubble stays
// and what it says, one line picked at random. The built-in ones come first, a player's own after them. The timing
// is in nudge.ts, the bubble in stores/nudge.ts.

export interface Reminder {
  /** A built-in's id (PRESETS), or `my-…` for one the player made. */
  id: string;
  name: string;
  on: boolean;
  /** Minutes at the computer between two of it. */
  everyMin: number;
  /** Seconds its bubble stays up. */
  showSec: number;
  lines: string[];
}

export const EVERY_MIN = { min: 5, max: 480 };
export const SHOW_SEC = { min: 5, max: 120 };
export const NAME_MAX = 8;
export const LINE_MAX = 30;
export const LINES_MAX = 12;
export const REMINDERS_MAX = 24;

/**
 * The built-in reminders, as a new player has them: water and getting up on, the rest there to be turned on. The
 * kinds and their minutes follow what break reminders ship with (Stretchly, Safe Eyes, Workrave, Courant) and desk
 * work guidance (a break from the screen every hour, a look into the distance every 20 minutes); the lines are our
 * own. No line names a number of minutes, since the player sets them.
 */
export const PRESETS: readonly Reminder[] = [
  {
    id: "water", name: "喝水", on: true, everyMin: 120, showSec: 30,
    lines: [
      "该喝水啦，去接一杯吧", "喝口水歇一下吧", "好一阵没喝水了哦", "杯子空了吗？续一杯吧", "记得喝水哦",
      "小口小口喝几口水吧", "起身去倒杯温水吧", "嘴巴干不干？喝点水吧", "水杯放在手边了吗", "喝完这口再接着忙吧",
    ],
  },
  {
    id: "move", name: "起身", on: true, everyMin: 60, showSec: 30,
    lines: [
      "坐了好一阵啦，起来走走", "站起来伸个懒腰吧", "该起来活动活动啦", "起来走两圈再回来吧", "去窗边站一会儿吧",
      "站起来踮踮脚尖吧", "离开椅子溜达一下吧", "坐太久啦，起来晃晃", "去趟洗手间顺便走走吧", "起身倒杯水，走一走",
    ],
  },
  {
    id: "eyes", name: "远眺", on: false, everyMin: 20, showSec: 20,
    lines: [
      "看看远处，歇歇眼睛吧", "抬头看看窗外吧", "找个远一点的东西看看", "离开屏幕，望远处一会儿", "看看房间最远的那面墙",
      "盯屏幕好久啦，看看远处", "眼睛放远，数到二十吧", "看看天空或者远处的树", "看远一点，数完再回来",
    ],
  },
  {
    id: "blink", name: "闭眼", on: false, everyMin: 40, showSec: 30,
    lines: [
      "闭上眼睛歇几秒吧", "眨眨眼，慢慢眨十下", "使劲眨眨眼吧", "闭眼数五个数再睁开", "搓热手心捂捂眼睛吧",
      "合上眼，听听周围的声音", "眼睛累了就闭一会儿", "闭着眼转转眼珠吧",
    ],
  },
  {
    id: "neck", name: "脖子", on: false, everyMin: 45, showSec: 30,
    lines: [
      "转转肩膀和脖子吧", "头慢慢歪向左边，再右边", "低头看看脚尖，再抬起来", "慢慢往左右转转头", "下巴往回收一收",
      "脖子僵了吧？慢慢活动下", "抬头看看天花板吧", "头别往前探啦，往回收收",
    ],
  },
  {
    id: "shoulder", name: "肩膀", on: false, everyMin: 45, showSec: 30,
    lines: [
      "耸耸肩，再放下来", "肩膀往后转几圈吧", "把肩膀放松，别端着啦", "两手背后十指交叉，挺挺胸", "肩胛骨往中间夹一夹",
      "胳膊抱到胸前拉一拉", "像风车一样抡抡胳膊", "双手举高，伸个大懒腰",
    ],
  },
  {
    id: "wrist", name: "手腕", on: false, everyMin: 40, showSec: 30,
    lines: [
      "握拳，再把手指张开", "转转手腕，正反各几圈", "甩甩手，放松一下", "挨个捏捏手指头吧", "打字好久啦，歇歇手吧",
      "双手合十，慢慢往下压", "拇指和每根手指碰一碰", "放下鼠标，手搭腿上歇歇",
    ],
  },
  {
    id: "posture", name: "坐姿", on: false, everyMin: 30, showSec: 30,
    lines: [
      "坐直一点，背靠椅背", "驼背啦，挺一挺", "两脚踩实地面了吗", "屏幕太近了吗？往后坐坐", "坐久了，挪挪身子吧",
      "肩膀放平，别歪着坐", "往里坐坐，靠好椅背", "头别凑那么近啦",
    ],
  },
  {
    id: "breathe", name: "深呼吸", on: false, everyMin: 60, showSec: 30,
    lines: [
      "慢慢吸气，再慢慢吐气", "停一下，深呼吸几次吧", "闭上眼，数几次呼吸", "吸气数四下，呼气数六下", "牙咬紧了吗？松一松",
      "想一件今天开心的小事", "先别急，喘口气再忙", "眉头松一松，深呼吸",
    ],
  },
  {
    id: "back", name: "腰背", on: false, everyMin: 90, showSec: 30,
    lines: [
      "站起来，双手往上够够", "叉着腰往后仰一仰吧", "坐着往左右扭扭腰", "弯腰，手往脚尖够一够", "扶着桌子做几个下蹲吧",
      "双手交叉举过头顶", "腰累了吧？起来扭一扭",
    ],
  },
  {
    id: "screen", name: "长休息", on: false, everyMin: 240, showSec: 30,
    lines: [
      "今天对着屏幕挺久啦", "已经忙了好久，歇会儿吧", "出去走走，晒晒太阳吧", "离开电脑十分钟好不好", "今天辛苦啦，休息一下吧",
      "去外面看看，透透气吧", "放下工作，喝杯茶吧", "剩下的歇一会儿再做吧",
    ],
  },
];

/**
 * Built-in reminders a break from the computer already answers: after one (no input for nudge.AWAY_MS, or a rest of
 * the tomato timer) their counts start over. Water and a player's own keep counting across a break.
 */
export const REST_ANSWERS: ReadonlySet<string> = new Set([
  "move", "eyes", "blink", "neck", "shoulder", "wrist", "posture", "breathe", "back", "screen",
]);

const text = (value: unknown, max: number) => (typeof value === "string" ? [...value.trim()].slice(0, max).join("") : "");
const within = (value: unknown, range: { min: number; max: number }, fallback: number) =>
  (typeof value === "number" && Number.isFinite(value) ? Math.min(range.max, Math.max(range.min, Math.round(value))) : fallback);

/** A copy of the built-in reminder [id] as it ships. */
export function presetOf(id: string): Reminder | undefined {
  const preset = PRESETS.find((p) => p.id === id);
  return preset && { ...preset, lines: [...preset.lines] };
}

/** The lines of [reminder] that say something; its name when none does. */
export function linesOf(reminder: Reminder): string[] {
  const lines = reminder.lines.map((line) => line.trim()).filter(Boolean);
  return lines.length ? lines : [reminder.name];
}

function cleanReminder(raw: unknown): Reminder | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Partial<Record<keyof Reminder, unknown>>;
  if (typeof r.id !== "string" || !/^[a-z0-9-]{1,24}$/.test(r.id)) return null;
  const preset = presetOf(r.id);
  // A built-in keeps the name it ships with, so a later version can rename it.
  const name = preset?.name ?? text(r.name, NAME_MAX);
  if (!name) return null;
  const lines = (Array.isArray(r.lines) ? r.lines : []).map((line) => text(line, LINE_MAX)).filter(Boolean).slice(0, LINES_MAX);
  return {
    id: r.id,
    name,
    on: typeof r.on === "boolean" ? r.on : (preset?.on ?? true),
    everyMin: within(r.everyMin, EVERY_MIN, preset?.everyMin ?? 60),
    showSec: within(r.showSec, SHOW_SEC, preset?.showSec ?? 30),
    lines: lines.length ? lines : (preset?.lines ?? [name]),
  };
}

/** The stored reminders made safe to use, in the player's order; built-in ones the list lacks are added as shipped. */
export function cleanReminders(raw: unknown): Reminder[] {
  const out: Reminder[] = [];
  for (const item of Array.isArray(raw) ? raw : []) {
    const reminder = cleanReminder(item);
    if (reminder && !out.some((r) => r.id === reminder.id) && out.length < REMINDERS_MAX) out.push(reminder);
  }
  for (const preset of PRESETS) if (!out.some((r) => r.id === preset.id)) out.push(presetOf(preset.id)!);
  return out;
}

/** A reminder of the player's own, not yet in [list]. */
export function newReminder(list: readonly Reminder[], now = Date.now()): Reminder {
  let id = `my-${now.toString(36)}`;
  while (list.some((r) => r.id === id)) id += "x";
  return { id, name: "我的提醒", on: true, everyMin: 60, showSec: 30, lines: [""] };
}
