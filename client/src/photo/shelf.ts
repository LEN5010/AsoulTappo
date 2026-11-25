// The shelf of the photocards' page: the box of a series, four of its cards fanned out behind it, one more coming up in
// the middle of them, and a sealed bag before it. A box that waits to be opened has its bags in it, and stands open once
// some of them are gone. It stands on paper, so the canvas is clear around it.
// Sizes are the opening's design units and the eye is as far away, so a box handed to the table looks the same there.
// Nothing here runs by itself: the host calls next() to bring up another card, and draws while `busy`.
import type { CardInfo, SeriesArt } from "./art";
import type { Scene } from "./engine";
import { lens, P, pose, type GL, type Pose, type Vec2 } from "./gl";
import type { Kit } from "./kit";
import { clamp, lerp, RAD } from "./math";
import {
  BAG, bagModel, BOX, boxModel, CARD_H, CARD_W, cardModel, groundShade, MM, PLUM,
  type BagModel, type BoxModel, type CardModel, type Painter,
} from "./painter";
import type { BoxPlace, CardPlace } from "./place";
import { createTimeline, E } from "./time";

export interface Face { card: string; signed: boolean }
export interface ShelfSound {
  slide(amount: number, rate: number, pan?: number): void;
  rustle(n: number, ms: number, amount: number, rate: number): void;
  lid(): void;
  thud(): void;
  flip(amount: number, rate: number, pan?: number): void;
}
export interface ShelfOptions {
  art: SeriesArt;
  /** What can come up, in the series' order. */
  cards: readonly Face[];
  calm?: boolean;
  sound?: ShelfSound;
  /** The host on the screen. */
  rect(): DOMRect;
  /** The middle of what is shown, in CSS pixels from the host's, and CSS pixels to a design unit. */
  place(): { x: number; y: number; scale: number };
  /** A card comes up in the middle. */
  on(front: Face): void;
}
export type ShelfHit = { kind: "box" | "bag" } | ({ kind: "card"; place: CardPlace } & Face);
export interface Shelf extends Scene {
  /** What it shows first is loaded. */
  readonly ready: Promise<void>;
  /** What the pointer is on. */
  readonly over: "box" | "bag" | "card" | "none";
  /** The box is being turned by hand. */
  readonly held: boolean;
  /** Comes into sight: the box settles, the cards fan out, the bag slides in. */
  enter(): void;
  /** Is there, as it stands once it has come in. */
  stand(): void;
  /** Another card comes up in the middle. */
  next(): void;
  /** Bags left of a box that waits to be opened, and how many it had; null without one. */
  waiting(left: number | null, of: number): void;
  /** Brings up cards of [faces] only; null for any. */
  only(faces: readonly Face[] | null): void;
  /** Another series takes its place, from the right (1) or from the left, with what waits of it. */
  change(art: SeriesArt, faces: readonly Face[], dir: -1 | 1, left: number | null, of: number): void;
  /** The cards and the bag go into the box and it shuts; done as it begins to turn back. */
  pack(): Promise<void>;
  /** They come out again. */
  unpack(): void;
  /** The cards go down behind a box that waits, for it to leave alone. */
  stow(): Promise<void>;
  /** The box leaves: where it is now. */
  hand(): BoxPlace;
  /** Where a box that waits stands; where a new one will ([fresh]). */
  place(fresh?: boolean): BoxPlace;
  /** The box is back, or there is a new one; [stands]: it was put in its place. */
  back(stands?: boolean): void;
  /** A card is looked at closely: it is not here meanwhile. */
  take(face: Face | null): void;
  move(x: number, y: number, t: number): void;
  down(x: number, y: number, t: number): void;
  up(): ShelfHit | null;
  leave(): void;
  dispose(): void;
}

/** What it takes up, in design units; its middle is that far above the middle of that. */
export const SHELF_ROOM = { w: 376, h: 492, cy: 4 };
/** Where the box stands, from its middle. */
export const SHELF_FOOT = { x: 14, y: 211.6 };

/** A card of the fan: which of its slots, and how far it has come up out of the box's back, 0 to 1. */
interface Side { slot: number; face: Face; model: CardModel; out: number; lift: number }
/** The card in the middle: how far up it is, and how far a sideways one has swung level. */
interface Middle { face: Face; model: CardModel; up: number; level: number; lift: number }

// The fan: cards about a pivot low behind the box, every few degrees.
const FAN = { step: 10.6, reach: 243, pivot: 148, s: 0.56, z: -60, sunk: 190 };
const FAN_ORDER = [0, 3, 1, 2];
const MIDDLE = { s: 0.62, z: -20, hidden: 94, tall: -122, wide: -104, lean: -3 };
/** The box shut, and one that waits open: leaning a little more toward us, to look into it. */
const REST = { x: 14, y: 92, rx: -9, ry: -26, s: 0.58 };
const OPEN = { x: 14, y: 98, rx: -15, ry: -24, s: 0.58 };
const SHUT = { lid: 90, tuck: -90, flaps: 90 };
const WIDE = { lid: 217, tuck: -34, flaps: -24 };
const BAG_REST = { x: -104, y: 158, z: 0, rx: -6, ry: 18, rz: -11, s: 0.44 };
const BOX_LIT = 1.06, BAG_LIT = 1.4;
/** Where the light falls from while no pointer is here. */
const LAMP: Vec2 = [-120, -160];
/** How cards lean while nothing leans them: the light on them is off their middle. */
const TILT: Vec2 = [0.5, -0.5];
/** It sways for this long after the pointer was last here, then eases to a stop. */
const AWAKE_MS = 20_000;
const DROWSE_MS = 2600;
/** A press that moved less than this is a tap. */
const TAP = 6;

/** A bag standing in a box, the [i]th of [of], drawn out of it by [rise]. */
function standing(box: BoxModel, i: number, of: number, rise: number): Pose {
  const m = pose(box.p), y = -rise * BOX[1] * 0.98 - 2.5 * MM, z = BOX[2] * (0.42 - (i / Math.max(1, of - 1)) * 0.84);
  return P(m[4] * y + m[8] * z + m[12], m[5] * y + m[9] * z + m[13], {
    z: m[6] * y + m[10] * z + m[14], rx: box.p.rx, ry: box.p.ry, rz: box.p.rz, s: box.p.s,
  });
}
const same = (a: Face, b: Face) => a.card === b.card && a.signed === b.signed;

export function createShelf(gl: GL, kit: Kit, painter: Painter, opts: ShelfOptions): Shelf {
  const { calm = false, sound, rect, on } = opts;
  let art = opts.art;
  let faces = [...opts.cards];
  const time = createTimeline();
  let dead = false;
  /** Runs a fresh number each time a longer move begins, so what an earlier one still had to do is dropped. */
  let round = 0;

  let view = { w: 480, h: 560, px: 1, css: 1, x: 0, y: 0 };
  /** The whole of it: aside while one series makes way for another. */
  const group = { x: 0 };
  const box = { ...REST, rz: 0, ...SHUT, stir: 0, drop: 0 };
  const bag: BagModel = bagModel({ info: art.cards[0] }, 4.2, 0);
  const bagAt = { ...BAG_REST, on: 1, lift: 0 };
  /** "in": between the box's back and its front. */
  let bagLayer: "front" | "in" | "gone" = "front";
  let sides: Side[] = [];
  let mid: Middle | null = null;
  let left: number | null = null;
  let size = 20;
  let packed = false;
  let handed = false;
  let taken: Face | null = null;
  let allowed: readonly Face[] | null = null;
  /** The series on its way here. */
  let coming: { art: SeriesArt; faces: readonly Face[]; left: number | null; size: number } | null = null;
  /** What waits until it has arrived or was put in its place; null while none is on its way. */
  let way: (() => void)[] | null = null;
  /** Raised by pack(), stow() and unpack(): of those that had to wait, only the last still counts. */
  let asked = 0;
  let cycle: Face[] = [];
  let at = -1;
  /** The middle card is on its way down or up. */
  let turning = false;
  let again = false;

  const shut = () => left === null || left >= size;
  const rest = () => (shut() ? REST : OPEN);
  const infoOf = (f: Face): CardInfo | undefined => (f.signed ? art.signed(f.card) : art.card(f.card));

  /* ---------------------------------------------------------------- which cards */
  /** Any stretch of the cycle has some of each kind. */
  function arrange(list: readonly Face[]): Face[] {
    const kinds = new Map<string, Face[]>();
    for (const f of list) {
      const info = infoOf(f);
      if (!info) continue;
      const k = f.signed ? "signed" : info.kind;
      kinds.set(k, [...(kinds.get(k) ?? []), f]);
    }
    const spread = [...kinds.values()].flatMap((l) => {
      // Not one member after the other: by twos and threes across the kind.
      const step = l.length > 4 ? 5 : 1, order = l.map((_, i) => l[(i * step) % l.length]);
      return (new Set(order).size === l.length ? order : l).map((f, i) => ({ f, at: (i + 0.5) / l.length }));
    });
    return spread.sort((a, b) => a.at - b.at).map((o) => o.f);
  }
  /** The members in turn, each with another picture. */
  function pickSides(): Face[] {
    const by = new Map<string, Face[]>();
    for (const f of faces) {
      const info = infoOf(f);
      if (!f.signed && info?.kind === "solo") by.set(info.back, [...(by.get(info.back) ?? []), f]);
    }
    const members = [...by.values()], out: Face[] = [];
    for (let i = 0; out.length < FAN_ORDER.length && i < members.length * 4; i++) {
      const mine = members[(i + 1) % members.length], f = mine[(i + 1) % mine.length];
      if (!out.some((o) => same(o, f))) out.push(f);
    }
    return out;
  }
  /** A signed card of a member the fan has the fewest of. */
  function pickFirst(): Face | undefined {
    const list = pool();
    const count = (f: Face) => sides.filter((s) => s.model.info.back === infoOf(f)!.back).length;
    const signed = list.filter((f) => f.signed);
    const least = Math.min(...signed.map(count));
    const few = signed.filter((f) => count(f) === least && infoOf(f)!.back !== sides[2]?.model.info.back);
    return few[0] ?? signed[0] ?? list[0];
  }
  const pool = () => {
    const list = allowed?.length ? cycle.filter((f) => allowed!.some((a) => same(a, f))) : cycle;
    const free = list.filter((f) => !sides.some((s) => same(s.face, f)));
    return free.length > 1 ? free : list;
  };
  const makeCard = (info: CardInfo, amp: number): CardModel => (
    { ...cardModel(info), small: true, amp, signT: 2, tiltX: TILT[0], tiltY: TILT[1] });
  const makeMiddle = (f: Face): Middle => ({ face: f, model: makeCard(infoOf(f)!, 14), up: 0, level: 0, lift: 0 });

  function set(): Promise<void> {
    cycle = arrange(faces);
    allowed = null;
    at = -1;
    sides = pickSides().map((face, i) => (
      { slot: [-2, -1, 1, 2][i], face, model: makeCard(infoOf(face)!, 12), out: 0, lift: 0 }));
    const first = pickFirst();
    mid = first ? makeMiddle(first) : null;
    at = first ? cycle.indexOf(first) : -1;
    return load();
  }
  function shown(): CardInfo[] {
    return [...sides.map((s) => s.model.info), ...(mid ? [mid.model.info] : [])];
  }
  async function load(): Promise<void> {
    await Promise.all([kit.ink(art.id), kit.signs(art.id), ...shown().map((info) => kit.small(info).ready)]);
  }

  /* ---------------------------------------------------------------- the middle card */
  async function turnTo(face: Face): Promise<void> {
    if (!mid || turning) return;
    turning = true;
    const mine = round, was = mid, info = infoOf(face)!;
    await kit.small(info).ready;
    if (dead || mine !== round) return;
    if (was.up > 0.02) {
      if (calm) was.up = 0;
      else {
        void time.tween(was, { level: 0 }, 300, E.flow);
        await time.tween(was, { up: 0, lift: 0 }, 400, E.flow);
      }
    }
    if (dead || mine !== round) return;
    mid = makeMiddle(face);
    kit.letGoSmall(shown(), 3);
    if (!packed && !handed) raise();
    turning = false;
    if (again) { again = false; next(); }
  }
  function raise(): void {
    if (!mid) return;
    on(mid.face);
    if (calm) { mid.up = mid.level = 1; return; }
    const wide = mid.model.info.land;
    void time.tween(mid, { up: 1 }, 760, E.out);
    void time.tween(mid, { level: 1 }, 620, E.flow, wide ? 130 : 0);
    // A band of light goes over it as it comes to rest.
    const c = mid.model;
    c.sheen = -0.6;
    c.sheenAmt = 0.22;
    void time.tween(c, { sheen: 1.9 }, 1100, E.flow, 420);
  }
  function next(): void {
    if (packed || handed || left !== null && !shut()) return;
    if (turning) { again = allowed !== null; return; }
    const list = pool();
    if (!list.length || list.length === 1 && mid && same(list[0], mid.face)) return;
    // The next of the cycle that may come up.
    for (let k = 1; k <= cycle.length; k++) {
      const f = cycle[(at + k + cycle.length) % cycle.length];
      if (!list.some((l) => same(l, f)) || mid && same(f, mid.face)) continue;
      at = (at + k) % cycle.length;
      void turnTo(f);
      return;
    }
  }

  /* ---------------------------------------------------------------- moves */
  /** The middle card stays away from a box that stands open: its lid is there. */
  const wantsMiddle = () => shut();
  function fanOut(delay = 0): void {
    if (calm) for (const s of sides) s.out = 1;
    else sides.forEach((s, i) => void time.tween(s, { out: 1 }, 900, E.out, delay + Math.abs(s.slot) * 70 + (i > 1 ? 30 : 0)));
  }
  function fanIn(ms = 420): void {
    if (calm) for (const s of sides) s.out = 0;
    else sides.forEach((s) => void time.tween(s, { out: 0, lift: 0 }, ms, E.flow, (2 - Math.abs(s.slot)) * 40));
  }
  function lower(ms = 340): void {
    if (!mid) return;
    if (calm) { mid.up = mid.level = 0; return; }
    void time.tween(mid, { level: 0 }, ms * 0.8, E.flow);
    void time.tween(mid, { up: 0, lift: 0 }, ms, E.flow);
  }
  function stand(to: Partial<typeof box>, ms: number, ease = E.flow, delay = 0): Promise<void> {
    if (calm) { Object.assign(box, to); return Promise.resolve(); }
    return time.tween(box, to, ms, ease, delay);
  }
  function putDown(): void {
    Object.assign(box, rest(), { rz: 0 }, shut() ? SHUT : WIDE, { stir: 0 });
    Object.assign(bagAt, BAG_REST, { on: left === null ? 1 : 0, lift: 0 });
    bagLayer = left === null ? "front" : "gone";
    Object.assign(spin, { yaw: 0, pitch: 0, vy: 0, vp: 0, held: false });
  }

  /** The series that was on its way is here. */
  function takeOver(): Promise<void> {
    if (!coming) return Promise.resolve();
    art = coming.art;
    faces = [...coming.faces];
    left = coming.left;
    size = coming.size;
    coming = null;
    bag.card = { info: art.cards[0] };
    const loaded = set();
    kit.letGoSmall(shown(), 2);
    return loaded;
  }
  /** Everything in its place, nothing on its way. */
  function settle(): void {
    void takeOver();
    round++;
    packed = handed = turning = again = false;
    time.clear();
    group.x = 0;
    putDown();
    wakeUp();
    arrive();
  }
  const here = () => new Promise<void>((go) => { way?.push(go); });
  function arrive(): void {
    const waiters = way ?? [];
    way = null;
    for (const go of waiters) go();
  }
  function atRest(): void {
    settle();
    for (const s of sides) s.out = 1;
    if (mid && wantsMiddle()) { mid.up = mid.level = 1; on(mid.face); }
  }
  /** It is in its place by then. */
  let arrived = 0;
  function enter(): void {
    if (calm) return atRest();
    settle();
    arrived = time.clock + 1250;
    for (const s of sides) s.out = 0;
    if (mid) mid.up = mid.level = 0;
    const to = rest();
    Object.assign(box, { y: to.y + 34, ry: to.ry - 26, s: to.s * 0.95 });
    void time.tween(box, { y: to.y, s: to.s }, 820, E.out);
    void time.tween(box, { ry: to.ry }, 1150, E.out);
    Object.assign(bagAt, { x: BAG_REST.x - 120, y: BAG_REST.y + 40, rz: BAG_REST.rz - 22 });
    void time.tween(bagAt, { x: BAG_REST.x, y: BAG_REST.y, rz: BAG_REST.rz }, 1000, E.out, 220);
    fanOut(160);
    if (wantsMiddle()) void time.wait(430).then(() => { if (!packed && !handed) raise(); });
  }

  async function pack(): Promise<void> {
    const ask = ++asked;
    if (way) await here();
    if (dead || ask !== asked) return;
    const mine = ++round;
    packed = true;
    turning = again = false;
    Object.assign(spin, { to: Math.round(spin.yaw / 360) * 360, held: false });
    if (calm) {
      lower();
      fanIn();
      bagLayer = "gone";
      return;
    }
    // The cards go down behind the box, the box turns to us and its lid goes back.
    sound?.slide(0.3, 1.1, -0.3);
    lower(320);
    fanIn(460);
    void stand({ ry: -12, rx: -17, y: 104, s: 0.585 }, 620, E.flow, 60);
    await time.wait(200);
    if (mine !== round) return;
    sound?.lid();
    void stand({ lid: 214 }, 560);
    void stand({ tuck: -34 }, 420, E.flow, 130);
    void stand({ flaps: -24 }, 400, E.flow, 210);
    await time.wait(200);
    if (mine !== round) return;
    // The bag goes up over it and down into it.
    sound?.rustle(6, 520, 0.12, 1);
    const over = standing(boxNow({ ry: -12, rx: -17, y: 104, s: 0.585 }), 2, size, 0.92);
    void time.tween(bagAt, { x: over.x }, 560, E.flow);
    void time.tween(bagAt, { y: over.y, z: over.z }, 560, E.quick);
    void time.tween(bagAt, { rz: 0, rx: -17, ry: -12, s: 0.585 }, 520, E.flow);
    await time.wait(470);
    if (mine !== round) return;
    bagLayer = "in";
    const inside = standing(boxNow({ ry: -12, rx: -17, y: 104, s: 0.585 }), 2, size, 0);
    sound?.slide(0.34, 0.9);
    void time.tween(bagAt, { x: inside.x, y: inside.y, z: inside.z }, 380, E.flow);
    await time.wait(260);
    if (mine !== round) return;
    // It shuts, gives a little, and turns back.
    void stand({ flaps: 90 }, 300);
    void stand({ lid: 90 }, 430, E.flow, 130);
    void stand({ tuck: -90 }, 330, E.flow, 220);
    await time.wait(430);
    if (mine !== round) return;
    sound?.thud();
    bagLayer = "gone";
    void stand({ y: 108 }, 90, E.flow).then(() => stand({ y: REST.y }, 420, E.out));
    void stand({ ry: REST.ry, rx: REST.rx, s: REST.s }, 460, E.flow, 60);
    await time.wait(260);
  }
  function unpack(): void {
    asked++;
    if (!packed) return;
    round++;
    packed = false;
    if (calm) {
      putDown();
      fanOut();
      if (wantsMiddle()) raise();
      return;
    }
    if (bagLayer === "front") {
      // Nothing was in it yet.
      void stand({ ...rest(), ...SHUT }, 460);
      void time.tween(bagAt, { ...BAG_REST }, 560, E.out);
    } else {
      // Out again, the way it went in.
      void stand({ lid: 214, ry: -12, rx: -17 }, 300);
      void stand({ tuck: -34, flaps: -24 }, 260, E.flow, 60);
      const mine = round;
      const open = boxNow({ ry: -12, rx: -17, y: REST.y, s: REST.s });
      const leaning = { rx: -17, ry: -12, rz: 0, s: 0.585 };
      const { x, y, z } = standing(open, 2, size, 0), over = standing(open, 2, size, 0.92);
      if (bagLayer === "gone") void time.tween(bagAt, { x, y, z, ...leaning }, 1);
      void time.wait(230).then(() => {
        if (mine !== round) return;
        bagLayer = "in";
        sound?.slide(0.3, 1);
        void time.tween(bagAt, { x: over.x, y: over.y, z: over.z, ...leaning }, 300, E.flow);
        return time.wait(280);
      }).then(() => {
        if (mine !== round) return;
        bagLayer = "front";
        void time.tween(bagAt, { ...BAG_REST }, 620, E.out);
        void stand({ flaps: 90 }, 300, E.flow, 80);
        void stand({ lid: 90 }, 420, E.flow, 190);
        void stand({ tuck: -90 }, 330, E.flow, 260);
        void stand({ ...REST }, 520, E.flow, 200);
      });
    }
    fanOut(240);
    if (wantsMiddle()) void time.wait(420).then(() => { if (!packed && !handed) raise(); });
  }
  async function stow(): Promise<void> {
    const ask = ++asked;
    if (way) await here();
    if (dead || ask !== asked) return;
    const mine = ++round;
    packed = true;
    turning = again = false;
    sound?.slide(0.26, 1.1);
    lower(300);
    fanIn(380);
    if (!calm) await time.wait(360);
    if (mine !== round) return;
  }
  const placeOf = (b: BoxModel): BoxPlace => {
    // While another view has the canvas, nobody says that the host's size has changed.
    const r = rect(), at = opts.place();
    view = { ...view, css: at.scale, x: at.x, y: at.y };
    return { cx: r.left + r.width / 2 + view.x + group.x * view.css, cy: r.top + r.height / 2 + view.y, css: view.css, box: b };
  };
  function boxNow(over: Partial<Pose> = {}): BoxModel {
    const b = boxModel(art.id, P(box.x, box.y, { rx: box.rx, ry: box.ry, rz: box.rz, s: box.s, ...over }));
    return Object.assign(b, { lid: box.lid + box.stir, tuck: box.tuck, flaps: box.flaps, lit: BOX_LIT });
  }
  /** As it is drawn: leaning, turned by hand, the lid stirring. */
  function boxSeen(): BoxModel {
    const b = boxNow();
    b.p.ry += lean.x * 7 + spin.yaw;
    b.p.rx += -lean.y * 4 + spin.pitch;
    b.p.x += lean.x * 1.5;
    return b;
  }

  /* ---------------------------------------------------------------- pointer */
  const ptr = { x: 0, y: 0, vx: 0, vy: 0, t: 0, inside: false, down: false, moved: 0 };
  const lean = { x: 0, y: 0 };
  const lamp = { x: LAMP[0], y: LAMP[1] };
  const spin = { yaw: 0, pitch: 0, vy: 0, vp: 0, to: 0, held: false };
  type Over = { kind: "box" | "bag" | "none" } | { kind: "card"; face: Face };
  let over: Over = { kind: "none" };
  let pressed: Over = over;
  /** When something last asked to be seen moving. */
  let woken = 0;
  function wakeUp(): void { woken = time.clock; }

  const sidePose = (s: Side): Pose => {
    const a = s.slot * FAN.step * s.out, reach = FAN.reach + s.lift * 9;
    return P(Math.sin(a * RAD) * reach + lean.x * -2.5, FAN.pivot - Math.cos(a * RAD) * reach + (1 - s.out) * FAN.sunk, {
      rz: a, s: FAN.s + 0.012 * s.lift, z: FAN.z,
    });
  };
  const midPose = (m: Middle): Pose => {
    const { land } = m.model.info;
    return P(lean.x * -1, lerp(MIDDLE.hidden, land ? MIDDLE.wide : MIDDLE.tall, m.up) - 7 * m.lift, {
      z: MIDDLE.z, s: MIDDLE.s + 0.014 * m.lift, rz: land ? lerp(-90, MIDDLE.lean, m.level) : 0,
    });
  };
  function inCard(m: CardModel, p: Pose, x: number, y: number): boolean {
    const w = (m.info.land ? CARD_H : CARD_W) * p.s / 2, h = (m.info.land ? CARD_W : CARD_H) * p.s / 2;
    const c = Math.cos(p.rz * RAD), s = Math.sin(p.rz * RAD), dx = x - p.x, dy = y - p.y;
    return Math.abs(dx * c + dy * s) < w && Math.abs(-dx * s + dy * c) < h;
  }
  function find(x: number, y: number): Over {
    if (bagLayer === "front" && Math.abs(x - bagAt.x) < BAG[0] * bagAt.s / 2 && Math.abs(y - bagAt.y) < BAG[1] * bagAt.s / 2) {
      return { kind: "bag" };
    }
    const bw = BOX[0] * box.s * 0.62, bh = BOX[1] * box.s / 2;
    if (Math.abs(x - box.x) < bw && y > box.y - bh - (shut() ? 6 : 44) && y < box.y + bh + 10) return { kind: "box" };
    if (mid && mid.up > 0.6 && !same(mid.face, taken ?? { card: "", signed: false }) && inCard(mid.model, midPose(mid), x, y)) {
      return { kind: "card", face: mid.face };
    }
    for (const i of [...FAN_ORDER].reverse()) {
      const s = sides[i];
      if (s && s.out > 0.6 && !(taken && same(s.face, taken)) && inCard(s.model, sidePose(s), x, y)) return { kind: "card", face: s.face };
    }
    return { kind: "none" };
  }
  const local = (x: number, y: number): Vec2 => [(x - view.x) / view.css - group.x, (y - view.y) / view.css];

  function move(cx: number, cy: number, t: number): void {
    const [x, y] = local(cx, cy);
    const dt = Math.max(1, t - (ptr.t || t - 16)), dx = x - ptr.x, dy = y - ptr.y, k = 1 - Math.exp(-dt / 40);
    ptr.t = t;
    ptr.vx += (dx / dt - ptr.vx) * k;
    ptr.vy += (dy / dt - ptr.vy) * k;
    ptr.x = x;
    ptr.y = y;
    ptr.inside = true;
    wakeUp();
    if (ptr.down) {
      ptr.moved += Math.hypot(dx, dy);
      if (spin.held) {
        spin.yaw += dx * 0.55;
        spin.pitch = clamp(spin.pitch - dy * 0.3, -46, 40);
      }
      return;
    }
    over = packed || handed ? { kind: "none" } : find(x, y);
  }
  function down(cx: number, cy: number, t: number): void {
    const [x, y] = local(cx, cy);
    Object.assign(ptr, { x, y, t, vx: 0, vy: 0, down: true, moved: 0, inside: true });
    wakeUp();
    over = pressed = packed || handed ? { kind: "none" } : find(x, y);
    if (pressed.kind === "box") Object.assign(spin, { held: true, vy: 0, vp: 0 });
  }
  function up(): ShelfHit | null {
    const was = ptr.down, tap = ptr.moved < TAP, hit = pressed;
    ptr.down = false;
    pressed = { kind: "none" };
    if (!was) return null;
    wakeUp();
    if (spin.held) {
      spin.held = false;
      spin.vy = tap ? 0 : clamp(ptr.vx * 0.55, -1.6, 1.6);
      spin.vp = tap ? 0 : clamp(-ptr.vy * 0.3, -0.8, 0.8);
      spin.to = Math.round((spin.yaw + spin.vy * 240) / 360) * 360;
      if (tap && left === null && !calm) void stand({ stir: 16 }, 240, E.out).then(() => stand({ stir: 0 }, 520, E.out));
    }
    if (!tap || hit.kind === "none") return null;
    if (hit.kind !== "card") return { kind: hit.kind };
    return { kind: "card", ...hit.face, place: cardPlace(hit.face) };
  }
  function cardPlace(face: Face): CardPlace {
    const m = mid && same(mid.face, face) ? mid : null, s = sides.find((o) => same(o.face, face));
    const p = m ? midPose(m) : s ? sidePose(s) : P(), info = infoOf(face)!, r = rect();
    return {
      x: r.left + r.width / 2 + view.x + (p.x + group.x) * view.css, y: r.top + r.height / 2 + view.y + p.y * view.css,
      w: (info.land ? CARD_H : CARD_W) * p.s * view.css, h: (info.land ? CARD_W : CARD_H) * p.s * view.css, rz: p.rz,
    };
  }

  /* ---------------------------------------------------------------- each frame */
  /** How much it sways: all of it while somebody is there, nothing a while after. */
  const life = () => (calm ? 0 : clamp(1 - (time.clock - woken - AWAKE_MS) / DROWSE_MS));
  let settled = false;

  function update(dt: number): void {
    time.advance(dt);
    ptr.vx *= Math.exp(-dt / 90);
    ptr.vy *= Math.exp(-dt / 90);
    const t = time.clock, k = 1 - Math.exp(-dt / 130), sway = life();
    const near = ptr.inside && !packed && !calm;
    const tx = near ? clamp(ptr.x / 230, -1, 1) : 0.4 * Math.sin(t / 2300) * sway;
    const ty = near ? clamp((ptr.y + 20) / 260, -1, 1) : (0.3 * Math.sin(t / 3100 + 1) - 0.1) * sway;
    const before = [lean.x, lean.y, lamp.x, lamp.y, spin.yaw, spin.pitch];
    lean.x += (tx - lean.x) * k;
    lean.y += (ty - lean.y) * k;
    const lx = near ? ptr.x : LAMP[0] + 60 * Math.sin(t / 1700) * sway, ly = near ? ptr.y : LAMP[1] + 40 * Math.sin(t / 2100) * sway;
    lamp.x += (lx - lamp.x) * k;
    lamp.y += (ly - lamp.y) * k;
    if (!spin.held) {
      for (let rest0 = dt; rest0 > 0; rest0 -= 8) {
        const h = Math.min(8, rest0);
        spin.vy += ((spin.to - spin.yaw) * 0.00005 - spin.vy * 0.011) * h;
        spin.yaw += spin.vy * h;
        spin.vp += (-spin.pitch * 0.00006 - spin.vp * 0.0125) * h;
        spin.pitch += spin.vp * h;
      }
      if (Math.abs(spin.yaw - spin.to) < 0.02 && Math.abs(spin.vy) < 0.0004) Object.assign(spin, { yaw: 0, to: 0, vy: 0 });
      if (Math.abs(spin.pitch) < 0.02 && Math.abs(spin.vp) < 0.0004) Object.assign(spin, { pitch: 0, vp: 0 });
    }
    // What the pointer is on comes up a little. The lid of a box that was not opened yet stirs.
    const on2 = over.kind === "card" ? over.face : null, kl = 1 - Math.exp(-dt / 90);
    let moving = 0;
    const lift = (o: { lift: number }, to: number) => {
      const d = to - o.lift;
      o.lift = Math.abs(d) < 0.002 ? to : o.lift + d * kl;
      moving += Math.abs(d);
    };
    for (const s of sides) lift(s, on2 && same(on2, s.face) ? 1 : 0);
    if (mid) lift(mid, on2 && same(on2, mid.face) ? 1 : 0);
    lift(bagAt, over.kind === "bag" ? 1 : 0);
    if (left !== null && shut() && !packed && !handed && sway) box.stir = 5 * sway * Math.max(0, Math.sin(t / 480)) ** 6;
    for (const c of [...sides.map((s) => s.model), ...(mid ? [mid.model] : [])]) {
      const kt = 1 - Math.exp(-dt / 100);
      c.tiltX += (TILT[0] * (1 - Math.abs(lean.x)) + lean.x * 0.75 - c.tiltX) * kt;
      c.tiltY += (TILT[1] * (1 - Math.abs(lean.y)) + lean.y * 0.7 - c.tiltY) * kt;
    }
    soften(dt);
    const after = [lean.x, lean.y, lamp.x, lamp.y, spin.yaw, spin.pitch];
    settled = moving < 0.004 && after.every((v, i) => Math.abs(v - before[i]) < (i === 2 || i === 3 ? 0.06 : 0.0008))
      && Math.abs(film.vx) + Math.abs(film.vy) < 0.0006;
  }
  /** The film of the bag bows with the way it is moved. */
  const film = { x: BAG_REST.x, y: BAG_REST.y, vx: 0, vy: 0 };
  function soften(dt: number): void {
    const hx = (bagAt.x - film.x) / Math.max(1, dt), hy = (bagAt.y - film.y) / Math.max(1, dt), h = Math.min(dt, 32);
    film.x = bagAt.x;
    film.y = bagAt.y;
    film.vx += ((clamp(hx * 15, -20, 20) * 0.45 - bag.bx) * 0.00012 - film.vx * 0.0075) * h;
    film.vy += ((clamp(hy * 15, -20, 20) * 0.45 - bag.by) * 0.00012 - film.vy * 0.0075) * h;
    bag.bx += film.vx * h;
    bag.by += film.vy * h;
  }

  function drawCard(m: CardModel, p: Pose, shade: number): void {
    const w = (m.info.land ? CARD_H : CARD_W) * p.s, h = (m.info.land ? CARD_W : CARD_H) * p.s;
    painter.shadow(p.x + 4 - lean.x * 3, p.y + 10, w, h, p.rz, shade, 1.28, PLUM);
    painter.solid();
    painter.clearDepth();
    painter.card(m, p);
  }
  function draw(): void {
    gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
    gl.enable(gl.BLEND);
    gl.depthFunc(gl.LEQUAL);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (handed) return;
    painter.begin({
      vp: lens(view.w, view.h, view.x / view.css + group.x, view.y / view.css), px: view.px, clock: time.clock,
      lamp: [lamp.x, lamp.y, 230], room: [lamp.x / 480 * 0.05, lamp.y / 320 * 0.035],
    });
    for (const i of FAN_ORDER) {
      const s = sides[i];
      if (s && s.out > 0.015 && !(taken && same(taken, s.face))) drawCard(s.model, sidePose(s), 0.24 * Math.min(1, s.out * 1.4));
    }
    if (mid && mid.up > 0.015 && !(taken && same(taken, mid.face))) drawCard(mid.model, midPose(mid), 0.30 * Math.min(1, mid.up * 1.6));

    const seen = boxSeen();
    groundShade(painter, seen);
    painter.solid();
    painter.clearDepth();
    painter.box(seen, BOX_LIT, "back");
    if (left !== null && !shut()) {
      for (let i = size - left; i < size; i++) painter.foil(bag, standing(seen, i, size, 0), 0, { low: true, lit: BOX_LIT });
    }
    if (bagLayer === "in") painter.foil(bag, bagPose(), 0, { lit: lerp(BAG_LIT, BOX_LIT, 0.6) });
    painter.box(seen, BOX_LIT, "front");

    if (bagLayer === "front") {
      const p = bagPose();
      painter.shadow(p.x + 6 - lean.x * 3, p.y + 10 + 4 * bagAt.lift, BAG[0] * p.s, BAG[1] * p.s, p.rz, 0.34, 1.26, PLUM);
      painter.solid();
      painter.clearDepth();
      painter.foil(bag, p, 0, { lit: BAG_LIT });
    }
  }
  const bagPose = (): Pose => P(bagAt.x + lean.x * 4, bagAt.y - 5 * bagAt.lift + lean.y * 1.5, {
    z: bagAt.z, rx: bagAt.rx - lean.y * 7, ry: bagAt.ry + lean.x * 10, rz: bagAt.rz, s: bagAt.s + 0.008 * bagAt.lift,
  });

  const ready = set();

  return {
    ready,
    get over() { return over.kind; },
    get held() { return spin.held; },
    get busy() {
      return turning || !!way || time.busy || ptr.down || !settled || life() > 0;
    },
    resize(w, h, dpr) {
      const p = opts.place();
      view = { w: w / p.scale, h: h / p.scale, px: p.scale * dpr, css: p.scale, x: p.x, y: p.y };
    },
    update, draw, enter, next, pack, unpack, stow, move, down, up,
    stand: atRest,
    waiting(n, of) {
      if (coming) {
        Object.assign(coming, { left: n, size: of });
        return;
      }
      const was = left;
      left = n;
      size = of;
      if (was === n || way || packed || handed) return;
      // Told while it comes in, it comes in again as it has to; else it stands that way at once.
      if (time.clock < arrived) return enter();
      settle();
      fanOut();
      if (wantsMiddle()) raise();
      else lower(1);
    },
    only(list) {
      allowed = list;
      if (!list || packed || handed || coming) return;
      wakeUp();
      if (mid && list.some((f) => same(f, mid!.face))) return;
      next();
    },
    change(nextArt, list, dir, n, of) {
      const mine = ++round;
      turning = again = false;
      wakeUp();
      coming = { art: nextArt, faces: list, left: n, size: of };
      way ??= [];
      const swap = async () => {
        await takeOver();
        if (dead || mine !== round) return;
        enter();
        if (!calm) {
          group.x = dir * 420;
          void time.tween(group, { x: 0 }, 780, E.out);
        }
      };
      if (calm) { void swap(); return; }
      sound?.slide(0.3, 0.9, -dir * 0.3);
      lower(260);
      fanIn(260);
      void time.tween(group, { x: -dir * 520 }, 420, E.flow);
      void time.wait(430).then(() => { if (mine === round) return swap(); });
    },
    hand() {
      const place = placeOf(boxSeen());
      handed = true;
      return place;
    },
    place(fresh = false) {
      const closed = fresh || shut(), { x, y, rx, ry, s } = closed ? REST : OPEN;
      return placeOf(Object.assign(boxNow({ x, y, rx, ry, s }), closed ? SHUT : WIDE));
    },
    back(stands = false) {
      // What was still moving when it left is not gone on with.
      settle();
      Object.assign(lean, { x: 0, y: 0 });
      over = { kind: "none" };
      for (const s of sides) s.out = 0;
      if (mid) mid.up = mid.level = 0;
      const late = stands ? 0 : 120;
      fanOut(late);
      if (left === null && !calm) {
        // There is another on the shelf.
        if (!stands) {
          Object.assign(box, { y: REST.y + 30, s: REST.s * 0.96 });
          void time.tween(box, { y: REST.y, s: REST.s }, 760, E.out);
        }
        Object.assign(bagAt, { x: BAG_REST.x - 120, y: BAG_REST.y + 40, rz: BAG_REST.rz - 22 });
        void time.tween(bagAt, { x: BAG_REST.x, y: BAG_REST.y, rz: BAG_REST.rz }, 1000, E.out, late + 40);
      }
      if (!wantsMiddle()) return;
      if (calm) raise();
      else void time.wait(late + 260).then(() => { if (!packed && !handed) raise(); });
    },
    take(face) { taken = face; },
    leave() {
      if (ptr.down) return;
      ptr.inside = false;
      over = { kind: "none" };
    },
    dispose() {
      dead = true;
      round++;
      time.clear();
      arrive();
      kit.letGoSmall([], 0);
    },
  };
}
