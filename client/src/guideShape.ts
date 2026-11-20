// The guide's marks (ui/GuideMark.vue): a loose pencil loop around a place and a curved arrow to it from the card.
// The loop is one hand-drawn shape, written out below as points around a unit circle, stretched over the place's
// box. Each card draws its marks a little differently (`variantOf`): the curl, the bow, the head and the loop's lean
// come from the card's name, so one card keeps its shape and the next one differs.

export interface Box { x: number; y: number; w: number; h: number }
export interface Ellipse { cx: number; cy: number; rx: number; ry: number }
interface Pt { x: number; y: number }

/** The ellipse a loop follows around [b]: wide enough to clear its corners, a little more so on a small box. */
export const ellipseAround = (b: Box): Ellipse =>
  ({ cx: b.x + b.w / 2, cy: b.y + b.h / 2, rx: b.w * 0.6 + 6, ry: b.h * 0.62 + 7 });

/**
 * One loop, clockwise from the upper left: [angle in degrees from three o'clock, downwards positive; radius as a share
 * of the ellipse's]. It goes round once and some more, coming back inside where it started, as a quick pencil does.
 */
const LOOP: readonly (readonly [number, number])[] = [
  [-152, 1.09], [-124, 1.04], [-92, 1.0], [-58, 1.02], [-26, 1.05], [4, 1.03], [34, 0.99], [64, 0.97],
  [94, 0.99], [124, 1.02], [152, 1.03], [182, 0.99], [212, 0.95], [238, 0.93], [256, 0.95],
];

/** How one card's marks differ from another's. */
export interface Variant {
  /** Where the curl starts along the arrow and how much of it the curl takes, as shares of the way. */
  curlAt: number;
  curlSpan: number;
  /** The curl's radius as a share of the arrow's length. */
  curlR: number;
  /** The arc's bow, times the usual. */
  bow: number;
  /** The arc and the curl go to the lower side of the line (the left of a line going straight up or down). */
  flip: boolean;
  /** The head's two strokes: angle (degrees) and length (px) of each. */
  head: readonly [number, number, number, number];
  /** The loop around the place: its lean and where it starts, in degrees. */
  tilt: number;
  turn: number;
  /** Desk cards: room between the card and its key for the arrow, and how far above the key the card's bottom sits. */
  room: number;
  rise: number;
}

/** The marks with nothing varied. */
export const PLAIN: Variant = {
  curlAt: 0.12, curlSpan: 0.3, curlR: 0.17, bow: 1, flip: false, head: [32, 12, -26, 10], tilt: -4, turn: 0, room: 100, rise: 36,
};

/** The variant of the card named [seed]: the same name, the same marks. */
export function variantOf(seed: string): Variant {
  // FNV-1a for the seed, mulberry32 for the numbers.
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  let a = h >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const between = (lo: number, hi: number) => lo + (hi - lo) * next();
  return {
    curlAt: between(0.08, 0.5),
    curlSpan: between(0.24, 0.34),
    curlR: between(0.14, 0.21),
    bow: between(0.7, 1.35),
    flip: next() < 0.3,
    head: [between(26, 38), between(10, 14), -between(20, 32), between(8, 12)],
    tilt: between(-9, 3),
    turn: between(-40, 40),
    room: Math.round(between(80, 128)),
    rise: Math.round(between(26, 50)),
  };
}

const f = (n: number) => Math.round(n * 10) / 10;

/** A smooth path through [pts] (Catmull-Rom as cubic Beziers). */
function through(pts: readonly Pt[]): string {
  let d = `M${f(pts[0]!.x)} ${f(pts[0]!.y)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)]!;
    const p1 = pts[i]!;
    const p2 = pts[i + 1]!;
    const p3 = pts[Math.min(pts.length - 1, i + 2)]!;
    d += `C${f(p1.x + (p2.x - p0.x) / 6)} ${f(p1.y + (p2.y - p0.y) / 6)} ${f(p2.x - (p3.x - p1.x) / 6)} ${f(p2.y - (p3.y - p1.y) / 6)} ${f(p2.x)} ${f(p2.y)}`;
  }
  return d;
}

/** The point at [deg] on [e] at [k] times its radius, leaning by [tilt] degrees. */
function onEllipse(e: Ellipse, deg: number, k = 1, tilt = PLAIN.tilt): Pt {
  const a = (deg * Math.PI) / 180;
  const x = e.rx * k * Math.cos(a);
  const y = e.ry * k * Math.sin(a);
  const l = (tilt * Math.PI) / 180;
  return { x: e.cx + x * Math.cos(l) - y * Math.sin(l), y: e.cy + x * Math.sin(l) + y * Math.cos(l) };
}

/** The loop around [e]. */
export const loopPath = (e: Ellipse, v: Variant = PLAIN): string =>
  through(LOOP.map(([deg, k]) => onEllipse(e, deg + v.turn, k, v.tilt)));

/** Shorter than this, the card sits on the loop and needs no arrow. */
const MIN_ARROW = 26;
/** Shorter than this, the arrow only bows; longer, it curls once on the way. */
const MIN_CURL = 40;
/** Where on the card's edge the arrow leaves from: kept this far from its corners. */
const CORNER = 18;

export interface Arrow { line: string; head: string }

/**
 * The arrow from [card] to the loop on [e]: from the card's edge that faces the loop (the end of it nearest the loop),
 * an arc with one curl near its tail, as a quick pencil arrow is drawn.
 *
 * After open hand-drawn arrows: the curl near the tail and the sweep to the head as in the loop arrows of
 * Eronred/handy-arrows (looked at only, not copied); the curl as a turning offset smoothed with a B-spline, the way
 * loopyArrow in bizweekgraphics/swoopyarrows (public domain) coils its line; the bow growing as the arrow gets
 * shorter, as getArrow in steveruizok/perfect-arrows (MIT) does.
 */
export function arrowPath(card: Box, e: Ellipse, v: Variant = PLAIN): Arrow | null {
  const right = card.x + card.w;
  const bottom = card.y + card.h;
  const along = (lo: number, hi: number, v: number) => Math.min(hi - CORNER, Math.max(lo + CORNER, v));
  let p0: Pt;
  if (e.cy - e.ry > bottom) p0 = { x: along(card.x, right, e.cx), y: bottom + 2 };
  else if (e.cy + e.ry < card.y) p0 = { x: along(card.x, right, e.cx), y: card.y - 2 };
  else p0 = { x: e.cx < card.x + card.w / 2 ? card.x - 2 : right + 2, y: along(card.y, bottom, e.cy) };
  const toward = (Math.atan2((p0.y - e.cy) / e.ry, (p0.x - e.cx) / e.rx) * 180) / Math.PI;
  const p3 = onEllipse(e, toward, 1.1);
  const len = Math.hypot(p3.x - p0.x, p3.y - p0.y);
  if (len < MIN_ARROW) return null;
  const pts = curlPoints(p0, p3, len, v);
  return { line: basis(pts), head: headAt(p3, pts[pts.length - 3]!, v.head) };
}

/**
 * Control points of an arrow from [p0] to [p3]: a quadratic arc that bows to the upper side of the line (to the right
 * of a line going straight up or down), more the shorter it is; long enough, it turns once round a curl a quarter of
 * the way along, on the same side.
 */
function curlPoints(p0: Pt, p3: Pt, len: number, v: Variant): Pt[] {
  const u = { x: (p3.x - p0.x) / len, y: (p3.y - p0.y) / len };
  let n = { x: -u.y, y: u.x };
  if (n.y > 0.001 || (Math.abs(n.y) <= 0.001 && n.x < 0)) n = { x: -n.x, y: -n.y };
  if (v.flip) n = { x: -n.x, y: -n.y };
  // The arc's control point: off the middle by a share of the length that shrinks from 0.32 (short) to 0.18 (200 px).
  const bow = v.bow * len * (0.32 - 0.14 * Math.min(1, Math.max(0, (len - 40) / 160)));
  const ctl = { x: (p0.x + p3.x) / 2 + n.x * bow, y: (p0.y + p3.y) / 2 + n.y * bow };
  const arc = (t: number): Pt => ({
    x: (1 - t) * (1 - t) * p0.x + 2 * (1 - t) * t * ctl.x + t * t * p3.x,
    y: (1 - t) * (1 - t) * p0.y + 2 * (1 - t) * t * ctl.y + t * t * p3.y,
  });
  const STEPS = 24;
  const pts: Pt[] = [];
  if (len < MIN_CURL) {
    for (let i = 0; i <= STEPS; i++) pts.push(arc(i / STEPS));
  } else {
    // One turn between these shares of the way: forwards, out to the side, back over itself and on.
    const from = v.curlAt;
    const to = v.curlAt + v.curlSpan;
    const r = Math.min(17, Math.max(9, len * v.curlR));
    for (let i = 0; i <= STEPS; i++) {
      const t = i / STEPS;
      const at = arc(t);
      if (t <= from || t >= to) {
        pts.push(at);
        continue;
      }
      // The tangent and the side at t, so the curl follows the arc.
      const a = arc(Math.max(0, t - 0.01));
      const b = arc(Math.min(1, t + 0.01));
      const d = Math.hypot(b.x - a.x, b.y - a.y) || 1;
      const tu = { x: (b.x - a.x) / d, y: (b.y - a.y) / d };
      let tn = { x: -tu.y, y: tu.x };
      if (tn.x * n.x + tn.y * n.y < 0) tn = { x: -tn.x, y: -tn.y };
      const phi = ((t - from) / (to - from)) * 2 * Math.PI;
      const off = { u: r * Math.sin(phi), n: r * (1 - Math.cos(phi)) };
      pts.push({ x: at.x + tu.x * off.u + tn.x * off.n, y: at.y + tu.y * off.u + tn.y * off.n });
    }
  }
  return pts;
}

/** A smooth path near [pts] (a uniform cubic B-spline from the first point to the last, like d3's curveBasis). */
function basis(pts: readonly Pt[]): string {
  const [first, second] = pts;
  if (!first || !second) return "";
  let d = `M${f(first.x)} ${f(first.y)}L${f((5 * first.x + second.x) / 6)} ${f((5 * first.y + second.y) / 6)}`;
  const seg = (a: Pt, b: Pt, c: Pt) => {
    d += `C${f((2 * a.x + b.x) / 3)} ${f((2 * a.y + b.y) / 3)} ${f((a.x + 2 * b.x) / 3)} ${f((a.y + 2 * b.y) / 3)} ${f((a.x + 4 * b.x + c.x) / 6)} ${f((a.y + 4 * b.y + c.y) / 6)}`;
  };
  for (let i = 2; i < pts.length; i++) seg(pts[i - 2]!, pts[i - 1]!, pts[i]!);
  const last = pts[pts.length - 1]!;
  seg(pts[pts.length - 2]!, last, last);
  d += `L${f(last.x)} ${f(last.y)}`;
  return d;
}

/** Two quick strokes at [tip], pointing away from [from]: a little uneven, as drawn. */
function headAt(tip: Pt, from: Pt, head: Variant["head"] = PLAIN.head): string {
  const len = Math.hypot(tip.x - from.x, tip.y - from.y) || 1;
  const back = { x: (from.x - tip.x) / len, y: (from.y - tip.y) / len };
  const turn = (deg: number, k: number): Pt => {
    const a = (deg * Math.PI) / 180;
    return { x: tip.x + (back.x * Math.cos(a) - back.y * Math.sin(a)) * k, y: tip.y + (back.x * Math.sin(a) + back.y * Math.cos(a)) * k };
  };
  const a = turn(head[0], head[1]);
  const b = turn(head[2], head[3]);
  return `M${f(a.x)} ${f(a.y)}L${f(tip.x)} ${f(tip.y)}L${f(b.x)} ${f(b.y)}`;
}
