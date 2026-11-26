// Opening a box: the purple box lands and opens, its silver bags come out, each is torn along its top and gives up one
// card, face down; a card turns over on its own, a sideways one (two members, or the group) stops the table and turns
// over in the dark. A signed one is held up while its signature is written.
// The light in a bag tells what is in it as it is torn: one colour for each member on the card, gold for a signed one.
// Nothing here touches the page: the host hands in the pointer and the keys, lets time pass and asks for the pictures.
import type { CardInfo, SeriesArt } from "./art";
import * as G from "./gl";
import { P, type GL, type Pose, type Vec2, type Vec3 } from "./gl";
import type { Kit } from "./kit";
import { clamp, lerp, RAD, smooth } from "./math";
import {
  BAG, bagModel, BOX, boxModel, CARD_H, CARD_W, cardModel, glowOf, groundShade, MM, PALE, STAGE_H, STAGE_W,
  type BagModel, type Bit, type Blend, type BoxModel, type CardModel, type Painter,
} from "./painter";
import { movePen } from "./pen";
import type { BoxPlace } from "./place";
import * as photoSound from "./sound";
import type { PhotoSound } from "./sound";
import { createTimeline, E } from "./time";

/** intro: the box lands and waits for a press. opening: it opens and moves aside. play: bags come and are torn. spot: a
 * rare one stops the table. gather: the row is laid out. end: the spread lies complete, or a card of it is looked at.
 * taking: one of them is on its way up or back. leaving: leave() was called. */
export type Phase = "intro" | "opening" | "play" | "spot" | "gather" | "end" | "taking" | "leaving";
/** An `index` is a bag's, or its card's, in the order of the deal. */
export type OpeningEvent =
  | { type: "phase"; phase: Phase }
  /** The seal is through: the bag counts as opened. */
  | { type: "torn"; index: number }
  /** Its card has come to rest face up: a signed one written, a sideways one turned over. */
  | { type: "shown"; index: number }
  /** It leaves for the row. */
  | { type: "kept"; index: number }
  | { type: "auto"; on: boolean }
  /** What stands over the table should step back for a rare card. */
  | { type: "dim"; on: boolean }
  /** A card of the spread is taken up, or put back. */
  | { type: "inspect"; index: number | null }
  /** The spread lies complete. */
  | { type: "end" }
  /** It stood still and stirs again on its own (a hint comes round): another picture is needed. */
  | { type: "stir" };

export interface OpeningOptions {
  art: SeriesArt;
  /** The bags in the order they come. */
  deal: readonly { card: string; signed: boolean }[];
  /** Bags that are open already: their cards lie in the row, their empties on the heap, and the next one comes. */
  opened?: number;
  /** Where its random numbers start. */
  seed?: number;
  /** The box opens by itself. */
  skipIntro?: boolean;
  /** Reduced motion: everything is laid out at once. */
  calm?: boolean;
  /** The box comes from there instead of dropping in, and the dark closes in on it. */
  from?: BoxPlace;
  /** The host on the screen, for what comes from outside or goes there. */
  rect?(): DOMRect;
  sound?: PhotoSound;
  /** Events come after createOpening has returned. */
  on?: (e: OpeningEvent) => void;
}
export interface OpeningState {
  phase: Phase;
  /** The bag under way. */
  cur: number;
  opened: number;
  active: { i: number; state: string; q: number; n: number; card: string } | null;
  shown: string | undefined;
  spot: string | null;
  tempo: number;
  /** Particles about. */
  fx: number;
  deal: string[];
  /** The context's error flag: asking for it waits for the driver. */
  readonly err: number;
}
/** Pointer places are in design units from the middle of the view; times are in milliseconds. */
export interface Opening {
  /** The view in CSS pixels, and device pixels to one of them. The canvas is the host's. */
  resize(cssW: number, cssH: number, dpr: number): void;
  down(x: number, y: number, t: number): void;
  move(x: number, y: number, t: number): void;
  /** [off]: the press was taken away (to scroll, say), so it is no tap. */
  up(off?: boolean): void;
  leavePointer(): void;
  /** What Space and Enter do; `repeat` while one is held. */
  press(repeat?: boolean): void;
  /** Bags are opened one after another by themselves. */
  setAuto(on: boolean): void;
  /** Cuts the run short. The first time while bags are being opened ("rush"): what is left comes out of the box in a row,
   * the cards of one member go down to the row at once and each rare one is opened as it would have been; a rare one on
   * show goes down first. Otherwise ("all"): every card goes to the row, and the row is laid out. Null when there is
   * nothing to cut short. Either way the box counts as opened from then on. */
  skip(): "rush" | "all" | null;
  /** Clears the table; resolves once it is empty. Nothing can be pressed any more. */
  leave(): Promise<void>;
  /** The same, and what lies under the table comes into sight, with another box coming down to [place]. */
  goOut(place?: BoxPlace): Promise<void>;
  /** The run ends with bags left: they stay in the box, which goes to [place], or away. */
  goBack(place?: BoxPlace): Promise<void>;
  /** The cards as they lie in the spread: their middles and sizes, in design units. */
  places(): { index: number; x: number; y: number; w: number; h: number }[];
  update(dt: number): void;
  draw(): void;
  state(): OpeningState;
  readonly clock: number;
  /** Something moves: another picture is needed. */
  readonly busy: boolean;
  /** [followed]: the next table needs the backs again. */
  dispose(followed?: boolean): void;
}

const TEETH = 30;
/** A box skipped through (rush()): how far apart its bags leave the box, how long each is on its way to the row and
 * where that row stands, how far apart those of one member are torn and how fast, how long a rare one takes to come up
 * into the hand and how long it is held there before it is torn. The steps are the draw board's (RevealScene: a tile
 * dealt every 42 ms, a quiet one turned every 70 ms, 300 ms from a turn to its spotlight). */
const RUSH_DEAL = 42, RUSH_OUT = 620, ROW_Y = -40, RUSH_STEP = 70, RUSH_TEAR = 200, RUSH_UP = 560, RUSH_BEAT = 300;
/** How long what sways by itself goes on after the last touch while the table waits. */
const STIR_MS = 3000;
/** Less than this from one picture to the next is no change. */
const STILL_EPS = 1e-3;
/** How fast the lid stirs, and where in its turn it begins to show. */
const LID_W = 2.1, LID_FROM = Math.asin(0.2);
/** How tall a card stands in the row. */
const RAIL_S = 98 / CARD_H;

type BagState = "box" | "rise" | "arrive" | "sealed" | "line" | "torn" | "falling" | "heap" | "gone";
type CardState = "in" | "pop" | "out" | "fly" | "rail" | "spread" | "inspect";
interface Place { x: number; y: number; s: number }
interface Card extends CardModel {
  state: CardState;
  /** Its place in the spread. */
  home: Place;
}
/** The way from the box to the middle, as a line, and how far along it things are. */
interface Route {
  pts: number[][];
  at: number[];
  clear: number;
  all: number;
  u: number;
  pose: { rx: number; ry: number; s: number };
  rz: number;
  /** How big the bag is at its end, and whether it ends in the row of a box skipped through. */
  size: number;
  line: boolean;
  /** The bag goes back along it. */
  back?: boolean;
}
interface Bag extends BagModel {
  card: Card;
  i: number;
  state: BagState;
  /** Where each bit of the seal gives, and how many have. */
  thr: Float32Array;
  n: number;
  rise: number;
  route: Route | null;
  /** Speeds of what springs. */
  vbx: number; vby: number; vw: number; curlV: number; tugV: number;
  tug: number;
  /** It is torn without a hand: by this much. */
  alone: boolean;
  drive: { q: number } | null;
  /** The run goes on. */
  resolve: (() => void) | null;
  /** Where it was in the last picture. */
  px?: number; py?: number;
  sealedAt: number;
  fade: number;
  float: number;
  leanX: number; leanY: number;
  /** It stands in the row of a box skipped through; it is torn there without a sound for each bit. */
  row: boolean;
  hush: boolean;
}
interface Table extends BoxModel {
  on: boolean;
  /** It sways about a lean, so much. */
  swaying: boolean; sway: number; rx0: number; ry0: number;
}
interface Spot { card: Card; group: boolean; sign: boolean; write: (() => void) | null; quick: boolean }
interface Mote extends Bit { vx: number; vy: number; g: number; vs: number; drag: number }
interface Scene {
  spot: number; dusk: number; warm: number;
  lights: readonly Vec3[];
  toneAmt: number;
  rays: number; rayAt: Pose;
  flash: number; flashTone: Vec3;
  /** How far the table covers what lies under it, and where it closes in on; the point things are seen straight from. */
  cover: number; coverAt: Vec2;
  lensX: number; lensY: number;
  /** The desk is lighter all over while light lies over it. */
  lift: number;
}
type Live = () => boolean;

export function createOpening(gl: GL, kit: Kit, painter: Painter, options: OpeningOptions): Opening {
  const { art, skipIntro = false, calm = false } = options;
  const snd: PhotoSound = options.sound ?? photoSound;
  const time = createTimeline();
  const { tween, wait } = time;
  const COUNT = options.deal.length;
  const FROM = Math.floor(clamp(options.opened ?? 0, 0, COUNT));

  let seed = options.seed ?? Math.floor(Math.random() * 1e9);
  function rand(): number {
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const rnd = (a: number, b: number) => a + (b - a) * rand();
  const pick = <V>(list: readonly V[]): V => list[Math.floor(rand() * list.length)];

  /* ---------------------------------------------------------------- what is there */
  function makeBag(i: number, card: Card): Bag {
    const thr = new Float32Array(TEETH);
    for (let k = 0; k < TEETH; k++) thr[k] = (k + 0.4 + rnd(-0.28, 0.28)) / TEETH;
    thr[0] = 0.045;                       // the notch has to be started
    thr[TEETH - 1] = 0.985;               // and the last bit holds on
    thr[TEETH - 2] = Math.min(thr[TEETH - 2], 0.94);
    return {
      ...bagModel(card, rnd(0, 20), rand() < 0.5 ? 0 : 1), card, i, state: "box", n: 0, thr, rise: 0, route: null,
      vbx: 0, vby: 0, vw: 0, curlV: 0, tug: 0, tugV: 0, alone: false, drive: null, resolve: null, sealedAt: 0, fade: 0,
      float: 0, leanX: 0, leanY: 0, row: false, hush: false,
    };
  }
  const makeCard = (info: CardInfo): Card => ({ ...cardModel(info), state: "in", home: { x: 0, y: 0, s: 1 } });
  function infoOf({ card, signed }: { card: string; signed: boolean }): CardInfo {
    const info = signed ? art.signed(card) : art.card(card);
    if (!info) throw new Error(`no card ${card}${signed ? " to sign" : ""} in ${art.id}`);
    return info;
  }

  const box: Table = {
    ...boxModel(art.id, P(0, -760, { rx: -14, ry: 26, s: 0.82 })), on: true, swaying: true, sway: 1, rx0: -14, ry0: 26,
  };
  const bags = options.deal.map(infoOf).map((info, i) => makeBag(i, makeCard(info)));
  const cards = bags.map((b) => b.card);
  const scene: Scene = {
    spot: 0, dusk: 0, warm: 0, lights: PALE, toneAmt: 0, rays: 0, rayAt: P(), flash: 0, flashTone: [1, 1, 1],
    cover: 1, coverAt: [0, 0], lensX: 0, lensY: 0, lift: 0,
  };
  const RANK = (c: Card) => (c.info.signed ? 3 : c.info.kind === "group" ? 2 : c.info.land ? 1 : 0);

  /** Raised when the run ends early, so what it still had queued falls silent. */
  let epoch = 0;
  let dead = false;
  let phase: Phase = calm || (FROM > 0 && FROM === COUNT) ? "gather" : FROM ? "play" : "intro";
  let cur = FROM - 1;
  let opened = FROM;
  let active: Bag | null = null;
  let shown: Card | null = null;
  /** A plain card turning over in the middle, before it waits there. */
  let spinning: Card | null = null;
  let spot: Spot | null = null;
  let inspecting: Card | null = null;
  let fx: Mote[] = [];
  let tempo = 0;
  let lastTear = -1e9;
  let auto = false;
  let eager = false;     // a swipe came while a card was still on its way out
  let early = false;     // so did a press
  let haste = 1;         // how fast a sideways card's ceremony runs; a press during it speeds it up
  let wides = 0;         // sideways cards so far in this box
  let view = { w: STAGE_W, h: STAGE_H, px: 1, css: 1 };
  /** Where the box comes from, until the size of the view is known. */
  let from = calm ? null : options.from ?? null;
  const visiting = !!from;
  let left: Promise<void> | null = null;      // leave() was called
  let rushing = false;   // skipped through: the row is out, or coming
  let rushNext = false;  // skipped while a rare card was on show: the row comes once it has gone down
  let released: (() => void) | null = null;

  /* ---------------------------------------------------------------- standing still */
  // While the table waits for a hand, what sways by itself (the box, a bag or a card held up, the light, the desk) slows
  // to a stop a while after the last touch, and once nothing moves no more pictures are asked for. The hints (the lid
  // that stirs, the mouth of a sealed bag) still come round: each wakes the table for as long as it plays.
  /** What sways by itself goes by this clock; it slows to a stop while the table waits. */
  let amb = 0;
  let ambRate = 1;
  /** The hints go by this one: it stands while nothing is drawn, and goes on at once to the next hint. */
  let hc = 0;
  /** When the table last moved by itself or was touched. */
  let stirred = 0;
  /** Nothing moves: no pictures are needed until a touch, or the next hint. */
  let still = false;
  let nap: ReturnType<typeof setTimeout> | null = null;
  let seen: number[] = [];

  /* ---------------------------------------------------------------- events */
  /** What happens while it is being made is told once it is. */
  let untold: OpeningEvent[] | null = [{ type: "phase", phase }];
  function emit(e: OpeningEvent): void {
    if (untold) untold.push(e);
    else if (!dead) options.on?.(e);
  }
  function setPhase(to: Phase): void {
    if (phase === to) return;
    phase = to;
    emit({ type: "phase", phase });
  }
  const isPhase = (p: Phase) => phase === p;
  let dimmed = false;
  function setDim(on: boolean): void {
    if (dimmed === on) return;
    dimmed = on;
    emit({ type: "dim", on });
  }
  function setInspecting(c: Card | null): void {
    inspecting = c;
    emit({ type: "inspect", index: c ? cards.indexOf(c) : null });
  }

  /* ---------------------------------------------------------------- pointer */
  const ptr = {
    x: 0, y: 0, vx: 0, vy: 0, down: false, sx: 0, sy: 0, far: 0, dir: 1, moved: 0, used: false, inside: false,
    t: undefined as number | undefined,
  };
  let pressWaiters: (() => void)[] = [];
  /** The next press, or a swipe that goes on from the last tear. */
  const pressed = () => new Promise<void>((done) => { pressWaiters.push(done); });
  function firePress(): void {
    const w = pressWaiters;
    pressWaiters = [];
    for (const f of w) f();
  }

  // A card turned by hand: it keeps going a little when let go of, and comes to rest on one of its faces.
  const turn = { card: null as Card | null, yaw: 0, pitch: 0, vy: 0, vp: 0, to: 0, held: false };
  const turnable = () => (phase === "end" ? inspecting : phase === "spot" && shown === spot?.card ? shown : null);
  /** What the hand turned becomes the card's own pose again. */
  function letTurnGo(c: Card): void {
    if (turn.card !== c) return;
    c.p.ry = ((c.p.ry + turn.yaw + 180) % 360 + 360) % 360 - 180;
    c.p.rx += turn.pitch * Math.sign(Math.cos(turn.yaw * RAD) || 1);
    Object.assign(turn, { card: null, yaw: 0, pitch: 0, vy: 0, vp: 0, held: false });
  }

  let grip: { y: number; q: number; far: number } | null = null;       // a tear in hand: where it began
  function onMove(x: number, y: number, t: number): void {
    const dt = Math.max(1, t - (ptr.t ?? t - 16));
    const dx = x - ptr.x, dy = y - ptr.y;
    ptr.t = t;
    const k = 1 - Math.exp(-dt / 40);
    ptr.vx += (dx / dt - ptr.vx) * k;
    ptr.vy += (dy / dt - ptr.vy) * k;
    ptr.x = x;
    ptr.y = y;
    ptr.inside = true;
    if (!ptr.down) return;
    ptr.moved += Math.hypot(dx, dy);
    if (turn.held) {
      turn.yaw += dx * 0.62;
      turn.pitch = clamp(turn.pitch - dy * 0.45, -80, 80);
      return;
    }
    if (active?.state === "sealed") return tearTo(active, x, y);
    // After a tear the same stroke may run on. Turning back asks for the next bag and hurries what is on the way.
    if ((y - ptr.far) * ptr.dir > 0) ptr.far = y;
    else if (Math.abs(y - ptr.far) > 44) {
      ptr.far = y;
      ptr.dir = -ptr.dir;
      hurry(0.9);
      if (shown) firePress();
    }
  }
  function onDown(x: number, y: number, t: number): void {
    snd.wake();
    Object.assign(ptr, { x, y, sx: x, sy: y, far: y, t, vx: 0, vy: 0 });
    Object.assign(ptr, { down: true, moved: 0, used: false, inside: true });
    grip = null;
    if (phase === "intro") { ptr.used = true; return pressBox(); }
    const card = turnable();
    if (card) {
      if (turn.card !== card) Object.assign(turn, { card, yaw: 0, pitch: 0, vy: 0, vp: 0, to: 0 });
      turn.held = true;
      return;
    }
    if (phase === "end") { ptr.used = true; return tapEnd(x, y); }
    if (active?.state !== "sealed") { ptr.used = true; ask(); }
  }
  /** One that comes while the box is on its way over counts once it is there. */
  function pressBox(): void {
    if (pressWaiters.length) firePress();
    else if (visiting) early = true;
  }
  /** A press while nothing can be taken hold of: go on, or get there sooner. */
  function ask(): void {
    if (spot?.write) spot.write();
    else if (spot && !shown) haste = 4;
    if (phase === "opening" || phase === "gather") haste = 3;
    hurry(0.6);
    if (pressWaiters.length) firePress();
    else if (phase === "play") early = true;
  }
  function hurry(k: number): void {
    if (phase !== "play" || active?.state === "sealed") return;
    tempo = Math.max(tempo, k);
    eager = true;
  }
  /** [off]: the press was taken away, so it is no tap. */
  function onUp(off: boolean): void {
    const was = ptr.down;
    ptr.down = false;
    if (!was) return;
    if (turn.held) {
      turn.held = false;
      if (ptr.moved < 6) return off ? undefined : inspecting ? void putBack() : ask();
      turn.vy = ptr.vx * 0.62;
      turn.vp = -ptr.vy * 0.45;
      turn.to = Math.round((turn.yaw + turn.vy * 240) / 180) * 180;
      return;
    }
    if (active?.state === "sealed") {
      const a = active;
      if (!ptr.used && !off && ptr.moved < 6) void tearAlone(a, 620);
      else if (a.q > 0.72) void tearAlone(a, 260);
    }
    grip = null;
  }
  function press(repeat: boolean): void {
    if (repeat && !shown && active?.state !== "sealed") return;
    snd.wake();
    if (phase === "intro") pressBox();
    else if (active?.state === "sealed") void tearAlone(active, 560);
    else if (inspecting) void putBack();
    // A key held down lets a plain card finish turning before it goes on; a press of its own sends it on at once.
    else if (repeat && spinning && spinning === shown) early = true;
    else ask();
  }
  function setAuto(on: boolean): void {
    if (auto !== on) {
      auto = on;
      emit({ type: "auto", on });
    }
    if (!on) return;
    if (active?.state === "sealed") void tearAlone(active, 420);
    else firePress();
  }

  /* ---------------------------------------------------------------- tearing */
  /** The flap follows the hand up: each bit of the seal gives once the hand is past it. */
  function tearTo(a: Bag, x: number, y: number): void {
    if (!grip) {
      // Only an upward pull lifts the flap; on the way down the hand just gets ready.
      if (y > ptr.sy) ptr.sy = y;
      if (ptr.sy - y < 5) return;
      grip = { y: ptr.sy, q: a.q, far: y };
      if (a.n === 0) a.gx = clamp((x - a.p.x) / BAG[0] + 0.5, 0.05, 0.95);
      a.hint = -2;
    }
    if (y < grip.far) grip.far = y;
    else if (y - grip.far > 18) { grip = null; ptr.sy = y; return; }
    const reach = 24 + 150 * (1 - grip.q);
    pull(a, grip.q + (1 - grip.q) * clamp((grip.y - y) / reach), clamp(Math.abs(ptr.vy) / 2.0));
  }
  function pull(a: Bag, q: number, speed: number): void {
    if (a.torn) return;
    let broke = 0;
    while (a.n < TEETH && q >= a.thr[a.n]) { breakTooth(a, speed); broke += 1; }
    const low = a.n ? a.thr[a.n - 1] : 0, high = a.n < TEETH ? a.thr[a.n] : 1;
    a.strain = clamp((q - low) / Math.max(0.01, high - low));
    if (broke) a.tugV += broke * 0.010;
    if (a.n >= TEETH) finishTear(a, speed);
  }
  function breakTooth(a: Bag, speed: number): void {
    const k = a.n;
    a.n += 1;
    a.q = a.n / TEETH;
    scene.lights = a.card.info.light;
    if (!a.hush) snd.tick(a.q, speed, (a.p.x + (a.gx - 0.5) * BAG[0]) / 480, k === 0 ? 1.3 : 1);
  }
  async function tearAlone(a: Bag, ms: number): Promise<void> {
    if (a.alone || a.torn || (a.state !== "sealed" && a.state !== "line")) return;
    a.alone = true;
    if (a.n === 0) a.gx = rnd(0.2, 0.8);
    a.hint = -2;
    const hand = { q: a.q };
    const my = epoch;
    a.drive = hand;
    await tween(hand, { q: 1.02 }, ms, (t) => 0.2 * t + 0.8 * E.flow(t));
    if (my === epoch && !a.torn) pull(a, 1.02, 0.7);
  }
  function finishTear(a: Bag, speed: number): void {
    a.torn = true;
    a.q = 1;
    a.strain = 0;
    a.state = "torn";
    // One of the row is no tear of the hand's: the pace and what was pressed stay as they were.
    if (!a.hush) {
      const gap = time.clock - lastTear;
      lastTear = time.clock;
      tempo = lerp(tempo, 1 - smooth(650, 2000, gap), 0.6);
      eager = early = false;
      ptr.far = ptr.y;
      ptr.dir = -1;
    }
    snd.snap(speed, (a.gx - 0.5) * 0.5);
    // The flap goes on up and over with the hand.
    a.curlV += 0.0008 + 0.0012 * speed;
    a.vw += 0.02;
    void tween(a, { air: 0.55 }, 900, E.flow);
    void tween(a, { beam: 1 }, RANK(a.card) ? 820 : 400, E.flow, RANK(a.card) ? 60 : 0);
    a.tugV -= 0.03;
    a.resolve?.();
    // A box skipped through counts as opened already.
    if (!rushing) emit({ type: "torn", index: a.i });
  }

  /* ---------------------------------------------------------------- particles */
  function sparks(x: number, y: number, n: number, tones: readonly Vec3[], reach = 0.5, size = 1): void {
    for (let i = 0; i < n; i++) {
      const a = rnd(0, Math.PI * 2), v = rnd(0.02, reach);
      const t = pick(tones), k = rnd(0.25, 0.8);
      const tint = (v2: number) => lerp(1, v2, 0.55) * k;
      fx.push({
        x: x + Math.cos(a) * 30, y: y + Math.sin(a) * 20, vx: Math.cos(a) * v, vy: Math.sin(a) * v * 0.8, g: 0.00012,
        size: rnd(7, 22) * size, kind: 1, c: [tint(t[0]), tint(t[1]), tint(t[2])],
        spin: rnd(0, 0.8), vs: rnd(-0.001, 0.001), life: 0, max: rnd(900, 2200), drag: 0.0022,
      });
    }
  }

  /** Dust in the light, rising out of the mouth of [b] over [ms]. */
  function motes(b: Bag, n: number, tones: readonly Vec3[], ms: number): void {
    for (let i = 0; i < n; i++) {
      const across = rnd(-0.40, 0.40), t = tones[Math.min(tones.length - 1, Math.floor((across + 0.5) * tones.length))];
      const k = rnd(0.30, 0.85);
      const tint = (v: number) => lerp(v, 1, 0.35) * k;
      fx.push({
        x: b.p.x + across * BAG[0], y: b.p.y - BAG[1] / 2 + rnd(-4, 10),
        vx: across * rnd(0.04, 0.16), vy: -rnd(0.05, 0.14), g: 0,
        size: rnd(5, 12), kind: 2, c: [tint(t[0]), tint(t[1]), tint(t[2])],
        spin: 0, vs: 0, life: -rnd(0, ms), max: rnd(1300, 2400), drag: 0.0007,
      });
    }
  }

  /* ---------------------------------------------------------------- the sequence */
  const railAt = (k: number): Pose => P((k - (COUNT - 1) / 2) * 33.5, 262, { s: 1, rz: 0 });
  const heapAt = (k: number): Pose => P(
    350 + (((k * 73) % 100) / 100 - 0.5) * 120, 120 - k * 1.1 + (((k * 41) % 100) / 100 - 0.5) * 56,
    { rz: ((k * 97) % 360) - 180, s: 0.36 },
  );
  const pace = (ms: number) => ms * lerp(1, 0.46, tempo) * (auto ? 0.62 : 1);
  /** Where a card lies in the row. */
  function rowPose(c: Card, k: number): Pose {
    const at = railAt(k);
    if (RANK(c)) at.y -= 13;       // like a card drawn up out of the row
    at.rz = c.info.land ? -90 : 0;
    at.s = RAIL_S;
    return at;
  }

  async function run(): Promise<void> {
    const my = epoch;
    const live: Live = () => my === epoch;
    if (calm) {
      for (let k = 0; k < COUNT; k++) {
        cards[k].state = "rail";
        cards[k].signT = 2;
        cards[k].p = railAt(k);
        bags[k].state = "gone";
      }
      box.on = false;
      opened = COUNT;
      return finale();
    }
    if (FROM) {
      if (visiting) await comeAside();
      else await wait(120);
      if (!live()) return;
      await play(live);
      if (live()) await finale();
      return;
    }
    if (visiting) await comeOver();
    else {
      // The box lands.
      await wait(120);
      if (!live()) return;
      void tween(box.p, { y: -6 }, 1250, E.out);
      await wait(620);
      if (!live()) return;
      snd.thud();
      await wait(360);
    }
    if (!live()) return;
    setPhase("intro");
    if (!skipIntro && !early) await pressed();
    if (!live()) return;
    early = false;
    setPhase("opening");
    // It turns to face us, the lid goes back.
    box.swaying = false;
    void tween(box.p, { ry: 0, rx: -17, y: 34, rz: 0 }, 760, E.flow);
    await wait(430);
    if (!live()) return;
    snd.lid();
    void tween(box, { lid: 217 }, 980, E.flow);
    void tween(box, { tuck: -34 }, 760, E.flow, 260);
    void tween(box, { flaps: -24 }, 720, E.flow, 420);
    await wait(760);
    if (!live()) return;
    // It moves aside, open, with the bags standing in it.
    void tween(box.p, { x: -338, y: 74, s: 0.52, ry: 15, rx: -19, rz: 0 }, 900, E.flow);
    snd.slide(0.4, 0.8, -0.2);
    snd.rustle(8, 700, 0.12, 0.9);
    await wait(870);
    if (!live()) return;
    haste = 1;
    setPhase("play");
    await play(live);
    if (live()) await finale();
  }
  /** Off the left edge, however wide the view is. */
  const boxAway = () => Math.min(-700, -view.w / 2 - 140);
  /** Puts the box where it comes from, as it is seen there. */
  function putFrom(f: BoxPlace): void {
    const r = options.rect?.();
    if (!r) return;
    const k = f.css / view.css, { x, y, z, s } = f.box.p;
    Object.assign(scene, {
      cover: 0, lensX: (f.cx - r.left - r.width / 2) / view.css, lensY: (f.cy - r.top - r.height / 2) / view.css,
    });
    Object.assign(box, { lid: f.box.lid, tuck: f.box.tuck, flaps: f.box.flaps, lit: f.box.lit, sway: 0 });
    box.p = { ...f.box.p, x: x * k, y: y * k, z: z * k, s: s * k };
    Object.assign(box, { rx0: box.p.rx, ry0: box.p.ry });
    scene.coverAt = [scene.lensX + box.p.x, scene.lensY + box.p.y];
    // What was opened comes after it, from out of sight.
    const away = Math.max(360, view.w / 2 - scene.lensX - 180);
    for (const { p } of bags.slice(0, FROM)) Object.assign(p, { x: p.x + away, rz: p.rz + 40 });
  }
  /** It comes over to the middle as the dark closes in on it. */
  async function comeOver(): Promise<void> {
    await wait(0);
    snd.slide(0.42, 0.72);
    void tween(scene, { cover: 1 }, 900, E.flow);
    void tween(scene, { lensX: 0, lensY: 0 }, 1060, E.flow);
    void tween(box.p, { x: 0, y: -6, z: 0, s: 0.82, rz: 0 }, 1060, E.flow);
    void tween(box, { rx0: -14, ry0: 26, lit: 1 }, 1060, E.flow);
    // Its lid is down by the time it sways again, and stirs.
    void tween(box, { lid: 90 }, 500, E.flow);
    void tween(box, { sway: 1 }, 900, E.flow, 520);
    await wait(1080);
  }
  /** One that stands open comes over to its place beside the table, and what was opened comes after it. */
  async function comeAside(): Promise<void> {
    await wait(0);
    box.swaying = false;
    snd.slide(0.4, 0.8, -0.2);
    void tween(scene, { cover: 1 }, 820, E.flow);
    void tween(scene, { lensX: 0, lensY: 0 }, 960, E.flow);
    void tween(box.p, { x: -338, y: 74, z: 0, s: 0.52, ry: 15, rx: -19, rz: 0 }, 960, E.flow);
    void tween(box, { lit: 1 }, 960, E.flow);
    if (FROM < COUNT) void tween(bags[FROM], { rise: 0.16 }, 620, E.flow, 240);
    const below = view.h / 2 - Math.min(0, scene.lensY);
    bags.slice(0, FROM).forEach(({ i, p, card: c }, k) => {
      const { x, rz } = heapAt(i * 2), at = rowPose(c, k);
      void tween(p, { x, rz: rz * 0.4 }, 760, E.out, 300 + k * 14);
      if (!thumbs.drawn || c.state !== "in") return;
      c.state = "rail";
      c.p = { ...at, y: Math.max(at.y, below) + 90 };
      void tween(c.p, { y: at.y }, 620, E.out, 320 + k * 18);
    });
    await wait(900);
  }
  /** The table as it is with the first [n] bags open. */
  function layOut(n: number): void {
    Object.assign(box, { lid: 217, tuck: -34, flaps: -24, swaying: false, p: P(-338, 74, { s: 0.52, ry: 15, rx: -19 }) });
    for (let k = 0; k < n; k++) {
      const b = bags[k], c = b.card, at = heapAt(b.i * 2);
      Object.assign(b, {
        state: "heap", torn: true, n: TEETH, q: 1, shown: 1, gx: rnd(0.2, 0.8), curl: 3.1, rad: 0.02, wave: 3.2,
        air: 0.34, open: 0.45, crush: 0.14, full: 0, fade: 1,
        p: P(at.x, at.y, { rz: at.rz * 0.4, s: at.s, rx: rnd(-14, 14), ry: rnd(-16, 16) }),
      });
      c.signT = 2;
      if (c.info.land) wides += 1;
    }
    // What comes from the shelf has none of them up yet.
    if (n < COUNT && !visiting) bags[n].rise = 0.16;
    // The row is there at once, or comes up as soon as there are pictures of it.
    const my = epoch, row = cards.slice(0, n);
    if (!thumbs.drawn) void thumbs.ready.then(() => { if (my === epoch) fillRow(row); });
    else if (!visiting) row.forEach((c, k) => { c.state = "rail"; c.p = rowPose(c, k); });
  }
  /** Where a bag is while it rises from the box: kept to the box's lean. */
  function riseAt(b: { i: number; rise: number }): Vec3 {
    const m = G.pose(box.p), y = -b.rise * BOX[1] * 0.98 - 2.5 * MM;
    const z = BOX[2] * (0.42 - (b.i / Math.max(1, COUNT - 1)) * 0.84);
    return [m[4] * y + m[8] * z + m[12], m[5] * y + m[9] * z + m[13], m[6] * y + m[10] * z + m[14]];
  }

  async function play(live: Live): Promise<void> {
    if (FROM < COUNT) kit.want(bags[FROM].card.info, "front");
    for (cur = FROM; cur < COUNT; cur++) {
      const b = bags[cur];
      for (let k = cur; k < Math.min(COUNT, cur + 3); k++) kit.want(bags[k].card.info, "front");
      kit.letGo(bags.slice(Math.max(0, cur - 1), cur + 3).map((x) => x.card.info));
      await arrive(b);
      if (!live()) return;
      await new Promise<void>((done) => {
        b.resolve = done;
        if (b.torn) done();
        else if (auto) void tearAlone(b, 420);
      });
      if (!live()) return;
      opened += 1;
      if (b.card.info.land) await revealWide(b, live);
      else if (b.card.info.signed) await revealSigned(b, live);
      else await revealSolo(b, live);
      if (!live()) return;
      if (rushNext) return void rush();
    }
  }

  /** The way from the box to the middle, as one line: straight up out of it, then over in a bow. Evenly measured, so
   * one curve of speed can run along the whole of it. */
  function route(b: Bag, to = [0, 24, 0], size = 1, line = false): Route {
    const from = riseAt(b), clear = riseAt({ i: b.i, rise: 1.04 });
    const up = [0, 1, 2].map((k) => clear[k] - from[k]), straight = Math.hypot(...up);
    const pts: number[][] = [[...from], [...clear]];
    const c1 = clear.map((v, k) => v + (up[k] / straight) * 120), c2 = [to[0] - 120, to[1] - 96, 46];
    for (let i = 1; i <= 28; i++) {
      const t = i / 28, s = 1 - t;
      pts.push([0, 1, 2].map((k) => (
        s * s * s * clear[k] + 3 * s * s * t * c1[k] + 3 * s * t * t * c2[k] + t * t * t * to[k])));
    }
    const at = [0];
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i], o = pts[i - 1];
      at.push(at[i - 1] + Math.hypot(p[0] - o[0], p[1] - o[1], p[2] - o[2]));
    }
    const pose = { rx: box.p.rx, ry: box.p.ry, s: box.p.s };
    return { pts, at, clear: at[1], all: at[at.length - 1], u: 0, pose, rz: rnd(-1.0, 1.0), size, line };
  }
  function follow(b: Bag, r: Route): void {
    const d = r.u * r.all;
    let i = 1;
    while (i < r.at.length - 1 && r.at[i] < d) i++;
    const k = clamp((d - r.at[i - 1]) / Math.max(1e-6, r.at[i] - r.at[i - 1]));
    const q = [0, 1, 2].map((n) => lerp(r.pts[i - 1][n], r.pts[i][n], k));
    // How far along the bow it is: it straightens up, grows, and leans into the turn.
    const w = clamp((d - r.clear) / (r.all - r.clear)), e = w * w * (3 - 2 * w);
    Object.assign(b.p, {
      x: q[0], y: q[1], z: q[2], rx: lerp(r.pose.rx, 0, e), ry: lerp(r.pose.ry, 0, e), s: lerp(r.pose.s, r.size, e),
      rz: 7 * Math.sin(Math.PI * w) * (1 - w) + r.rz * e,
    });
    if (b.state === "rise" && d > r.clear && !r.back) {
      if (r.line) b.state = "line";
      else {
        b.state = "arrive";
        active = b;
      }
    }
    if (r.back && d <= r.clear) {
      if (active === b) active = null;
      b.state = r.u > 0.004 ? "rise" : "box";
      if (b.state === "box") Object.assign(b, { route: null, rise: 0 });
    }
  }
  /** Draws [b] up out of the box onto its way, with the box giving a little. */
  function setOut(b: Bag, ms: number): Route {
    b.state = "rise";
    b.p = P();
    const r = b.route = route(b);
    follow(b, r);
    b.px = b.p.x;
    b.py = b.p.y;
    snd.rustle(5, ms * 0.6, 0.09, 1);
    void tween(box.p, { rz: -0.9, y: 71 }, ms * 0.22, E.flow)
      .then(() => tween(box.p, { rz: 0, y: 74 }, ms * 0.6, E.flow));
    return r;
  }
  /** The next bag stands up out of the box while the card before it is on show, so it is there as soon as that one
   * goes. */
  function lift(b: Bag | undefined): void {
    if (!b || b.state !== "box") return;
    kit.want(b.card.info, "front");
    kit.want(b.card.info, "behind");
    const r = setOut(b, pace(1060));
    // Short of where the bow begins: over it, it is the bag in hand.
    void tween(r, { u: Math.max(0, r.clear - 1) / r.all }, pace(560), E.flow);
  }
  async function arrive(b: Bag): Promise<void> {
    const my = epoch, ready = b.state === "rise" && !!b.route, ms = pace(ready ? 560 : 1060);
    b.resolve = null;
    const r = ready ? b.route! : setOut(b, ms);
    snd.slide(0.26, 0.95, -0.35);
    void tween(r, { u: 1 }, ms, E.glide).then(() => { if (b.route === r) b.route = null; });
    await kit.want(b.card.info, "front").ready;
    await kit.want(b.card.info, "behind").ready;
    // One that stood ready can be torn while it settles.
    await wait(ms * (ready ? 0.5 : 0.72));
    if (my !== epoch || active !== b) return;
    b.state = "sealed";
    grip = null;
    ptr.sx = ptr.x;
    ptr.sy = ptr.y;
    if (ptr.down) ptr.moved = 10;
    b.sealedAt = hc;
    // A press that came while the bag was on its way tears it.
    if (early && !ptr.down) void tearAlone(b, 420);
    early = false;
  }

  /** The next bag comes up a little in the box. */
  function peek(): void {
    const n = bags[cur + 1];
    if (n?.state === "box") void tween(n, { rise: 0.16 }, pace(620), E.flow);
  }

  /** The card shows itself at the mouth, back first: whose back it is already tells something. */
  function popCard(b: Bag): void {
    const c = b.card, land = c.info.land, s = b.row ? b.p.s : 1;
    c.state = "pop";
    c.p = P(b.p.x, b.p.y + 0.5 * MM * s, { ry: -180, rz: (land ? -90 : 0) + b.p.rz, s });
    c.lipOn = 1;
    void tween(b, { open: 1 }, pace(420), E.flow);
  }

  /** A rare bag, torn: the room goes dark, the bag sinks a little, and its light stands up out of the mouth before
   * anything else does. */
  async function pour(b: Bag, live: Live): Promise<boolean> {
    const c = b.card, kind = c.info.signed ? "sign" : c.info.kind, g = glowOf(c.info), group = kind === "group";
    setPhase("spot");
    spot = { card: c, group, sign: kind === "sign", write: null, quick: false };
    pressWaiters = [];
    early = eager = false;
    tempo = 0;
    // The first of a box, the group and a signed one take their time; later ones and the automatic run are brisker.
    haste = auto ? 1.4 : kind === "duo" && wides ? 1.2 : 1;
    if (c.info.land) wides += 1;
    setDim(true);
    scene.lights = c.info.light;
    scene.rayAt = P(0, -14);
    void tween(scene, { spot: 0.94, toneAmt: g.warm }, 900, E.flow);
    void tween(b, { open: 1 }, 620, E.flow);
    void tween(b.p, { y: b.p.y + 62 }, 900, E.flow);
    snd.slide(0.36, 0.62);
    if (kind !== "duo") {
      snd.slide(0.26, 0.46);
      motes(b, group ? 16 : 26, c.info.light, group ? 1100 : 1700);
    }
    await wait(kind === "duo" ? 520 : 740);
    return live();
  }
  /** The room as it was, and the card to its place in the row. */
  async function settleRare(c: Card): Promise<void> {
    void tween(scene, { spot: 0, toneAmt: 0, rays: 0 }, 760, E.flow);
    setDim(false);
    setPhase("play");
    shown = null;
    tempo = 0;
    keep(c);
    spot = null;
    lift(bags[cur + 1]);
    await wait(260);
  }

  /** A card of one member comes out of its bag and turns over; a signed one unhurried, in its own light. False once the
   * run has ended; "asked" when a press sent a plain one on before it had turned all the way. */
  async function soloOut(b: Bag, live: Live, grand = false): Promise<false | "seen" | "asked"> {
    const c = b.card, pc = grand ? (ms: number) => ms * 1.35 : pace;
    // The flap goes up first.
    if (!grand) await wait(pc(210));
    if (!live()) return false;
    popCard(b);
    peek();
    snd.slide(0.42, 1.1);
    void tween(c.p, { y: c.p.y - CARD_H * 0.17 }, pc(420), E.out);
    await wait(grand ? 560 : pc(auto || tempo > 0.5 ? 150 : 300));
    if (!live()) return false;
    // Out it comes, as the bag is drawn off it.
    snd.slide(0.5, 0.95);
    void tween(c.p, { y: -100, rz: 0 }, pc(460), E.flow);
    void dropBag(b, pc(1), 460);
    void tween(c, { bend: grand ? -4 : -7 }, pc(240), E.flow).then(() => tween(c, { bend: 0 }, pc(420), E.flow));
    if (grand) void tween(scene, { rays: 0.16 }, 900, E.flow);
    await wait(pc(370));
    if (!live()) return false;
    c.state = "out";
    // A press that came before it was out lets it turn over first, then sends it on.
    const queued = !grand && early;
    if (!grand) {
      early = false;
      shown = spinning = c;
      lift(bags[cur + 1]);
    }
    void tween(c, { lipOn: 0 }, pc(200));
    // Over it goes, rising a little and leaning into the turn; one sent on finishes the turn on its way to the row.
    const turning = () => c.state === "out";
    void tween(c.p, grand ? { y: -14, s: 1.36 } : { y: -26, s: 1.2 }, pc(760), E.flow);
    void tween(c.p, { z: grand ? 130 : 90 }, pc(380), E.flow)
      .then(() => { if (turning()) void tween(c.p, { z: grand ? 110 : 40 }, pc(420), E.flow); });
    void tween(c.p, { rz: -3.2 }, pc(320), E.flow)
      .then(() => { if (turning()) void tween(c.p, { rz: 0 }, pc(460), E.flow); });
    void tween(c.p, { ry: 0 }, pc(740), E.flow);
    if (grand) await wait(pc(330));
    else if (await waitOrPress(pc(330))) return sent(live);
    if (!live()) return false;
    snd.flip(0.75, 1);
    c.sheen = -0.5;
    c.sheenAmt = grand ? 0.14 : 0.26;
    void tween(c, { sheen: 1.9 }, pc(1000), E.flow, pc(120));
    let written: boolean | Promise<boolean> = true;
    if (grand) {
      // The pen is already on it as the face comes round.
      await wait(115);
      if (!live()) return false;
      written = write(c);
      void tween(scene, { rays: 0.10 }, 700, E.flow);
      await wait(pc(420) - 115);
    } else {
      if (await waitOrPress(pc(420))) return sent(live);
      spinning = null;
      if (queued) early = true;
    }
    return live() && await written && "seen";
  }
  /** A plain card sent on while it turned. */
  function sent(live: Live): false | "asked" {
    spinning = null;
    return live() && "asked";
  }
  /** The pen goes over the card; resolves once all of it is there. */
  function write(c: Card): Promise<boolean> {
    // What was pressed on the way here does not count: the writing would be over before it was seen.
    pressWaiters = [];
    early = eager = false;
    haste = auto ? 1.4 : 1;
    const ms = c.info.signed!.ms, since = time.clock, here = spot!;
    c.signT = 0;
    return new Promise((done) => {
      void tween(c, { signT: 1.02 }, ms * 1.02, E.linear).then(() => done(true));
      // A press writes the rest at once.
      here.write = () => {
        if (time.clock - since < 450 || here.quick) return;
        here.quick = true;
        void tween(c, { signT: 1.02 }, 320, E.flow).then(() => done(true));
      };
    });
  }
  /** A plain card stays until a press sends it to the row, at once however far it has turned; the next bag is ready. */
  async function revealSolo(b: Bag, live: Live): Promise<void> {
    const how = await soloOut(b, live);
    if (!how) return;
    if (how === "seen") {
      emit({ type: "shown", index: b.i });
      await hold(0, auto ? 320 : 0);
      if (!live()) return;
    }
    // The press that sent it on is spent: the next bag waits for one of its own.
    early = eager = false;
    pressWaiters = [];
    shown = null;
    keep(b.card);
  }

  /** A signed card comes up out of the gold, and is signed while it turns over. */
  async function revealSigned(b: Bag, live: Live): Promise<void> {
    const c = b.card;
    if (!await pour(b, live)) return;
    if (!await soloOut(b, live, true) || !live()) return;
    if (spot) spot.write = null;
    c.signT = 2;
    shown = c;
    // Light runs along the ink, and the room warms a little.
    c.gleamInk = -0.5;
    void tween(c, { gleamInk: 1.9 }, 1150, E.flow, 80);
    void tween(scene, { rays: 0.24, toneAmt: 0.42 }, 1100, E.flow);
    haste = 1;
    early = false;
    emit({ type: "shown", index: b.i });
    await hold(360, auto ? 1000 : 0);
    if (live()) await settleRare(c);
  }

  /** Waits [ms], or less if a press comes in the meantime: true then. */
  function waitOrPress(ms: number): Promise<boolean> {
    return new Promise((done) => {
      const go = () => done(true);
      pressWaiters.push(go);
      void wait(ms).then(() => {
        pressWaiters = pressWaiters.filter((f) => f !== go);
        done(false);
      });
    });
  }
  /** Holds a card on show until the next press; a run of quick tears does not wait long. */
  async function hold(least: number, autoMs: number): Promise<void> {
    const asked = pressed();
    await wait(least);
    if (autoMs) await Promise.race([asked, wait(autoMs)]);
    else if (!early && !(eager && ptr.down)) await asked;
    early = false;
    pressWaiters = [];
  }

  async function dropBag(b: Bag, k: number, ms = 460): Promise<void> {
    b.state = "falling";
    b.fade = 0;
    void tween(b, { fade: 1, full: 0 }, 420, E.flow);
    void tween(b, { beam: 0 }, RANK(b.card) ? 620 : 320, E.flow);
    // Air follows the card out.
    void tween(b, { air: 0.85 }, 760, E.flow);
    active = active === b ? null : active;
    b.route = null;
    const at = heapAt(b.i * 2);
    snd.rustle(5, 420, 0.12, 0.85);
    void tween(b.p, { y: b.p.y + 262 }, ms * k, E.flow);
    await wait(ms * 0.9 * k);
    // It is let go of, crumples a little and drifts over to the others.
    // With nothing in it, it goes nearly flat again.
    void tween(b, { crush: 0.14, open: 0.45, air: 0.34 }, 1100 * k, E.flow);
    void tween(b.p, { x: at.x, rz: at.rz * 0.4, s: at.s, rx: rnd(-14, 14), ry: rnd(-16, 16) }, 820 * k, E.flow);
    await tween(b.p, { y: at.y }, 820 * k, E.out);
    b.state = "heap";
    snd.rustle(2, 120, 0.12, 0.7);
  }

  /** [c] goes to its place in the row, the one of its bag in the deal. */
  function keep(c: Card): void {
    const k = cards.indexOf(c);
    void collect(c, k);
    emit({ type: "kept", index: k });
  }
  async function collect(c: Card, k: number): Promise<void> {
    c.state = "fly";
    letTurnGo(c);
    const at = rowPose(c, k);
    snd.slide(0.28, 1.2);
    // Across first, then down.
    void tween(c.p, { x: at.x }, pace(560), E.out);
    void tween(c.p, { rz: at.rz, s: at.s, z: 0, rx: 0, ry: 0 }, pace(560), E.flow);
    await tween(c.p, { y: at.y }, pace(560), E.flow);
    c.state = "rail";
    c.p.s = at.s;
    c.gleam = -0.6;
    void tween(c, { gleam: 2 }, 700, E.flow);
    snd.flip(0.28, 1.25, at.x / 480);
  }

  /* ---------------------------------------------------------------- a sideways card */
  // Its light has said how many are on it. It comes up out of the bag, swings level and turns over; the colours it
  // stood in go behind it, each on its own side.
  async function revealWide(b: Bag, live: Live): Promise<void> {
    const c = b.card, group = c.info.kind === "group";
    if (!await pour(b, live)) return;
    popCard(b);
    peek();
    snd.slide(0.5, 0.75);
    void tween(c.p, { y: c.p.y - CARD_H * 0.17 }, 620, E.out);
    await wait(group ? 620 : 520);
    if (!live()) return;
    snd.slide(0.5, 0.7);
    void tween(c.p, { y: -100 }, 760, E.flow);
    void dropBag(b, 1, 760);
    void tween(scene, { rays: group ? 0.24 : 0.17 }, 900, E.flow);
    await wait(640);
    if (!live()) return;
    c.state = "out";
    shown = null;
    void tween(c, { lipOn: 0 }, 260);
    // It swings level and comes close, and turns over on the way.
    void tween(c.p, { x: 0, y: -14, z: 120, s: 1.5 }, 1100, E.flow);
    void tween(c.p, { rz: 0 }, 1000, E.flow);
    snd.slide(0.32, 0.85);
    await wait(820);
    if (!live()) return;
    await turnWide(c, group);
    if (!live()) return;
    haste = 1;
    early = false;
    emit({ type: "shown", index: b.i });
    await hold(group ? 500 : 320, auto ? (group ? 1100 : 700) : 0);
    if (live()) await settleRare(c);
  }

  async function turnWide(c: Card, group: boolean): Promise<void> {
    const my = epoch;
    snd.slide(0.4, 0.9);
    void tween(c.p, { ry: 0, s: 1.6 }, 1250, E.flow);
    void tween(c.p, { z: 170 }, 600, E.flow).then(() => tween(c.p, { z: 120 }, 800, E.flow));
    await wait(470);
    if (my !== epoch) return;
    // The light comes up with the face.
    snd.flip(0.7, 0.85);
    void tween(scene, { rays: group ? 0.54 : 0.38, toneAmt: group ? 0.55 : 0.42 }, 1300, E.flow);
    c.sheen = -0.6;
    c.sheenAmt = group ? 0.34 : 0.28;
    void tween(c, { sheen: 2 }, 1500, E.flow, 260);
    if (group) sparks(0, -30, 10, c.info.tones, 0.12, 0.8);
    await wait(800);
    if (my === epoch) shown = c;
  }

  /* ---------------------------------------------------------------- the whole box laid out */
  function spreadPlan(): Map<Card, Place> {
    // The sideways ones on top, the rest in two rows under them, in the order they came.
    const wide = cards.filter((c) => c.info.land);
    const tall = cards.filter((c) => !c.info.land).sort((a, b) => RANK(b) - RANK(a));
    const plan = new Map<Card, Place>();
    const ww = Math.min(212, 860 / Math.max(1, wide.length) - 16), wh = ww * 54 / 86;
    wide.forEach((c, i) => plan.set(c, {
      x: (i - (wide.length - 1) / 2) * (ww + 16), y: -214 + (136 - wh) / 2, s: ww / CARD_H,
    }));
    const rows = Math.ceil(tall.length / 8), per = Math.ceil(tall.length / rows);
    const th = Math.min(150, 330 / rows), tw = th * 54 / 86;
    tall.forEach((c, i) => {
      const r = Math.floor(i / per), n = r < rows - 1 ? per : tall.length - per * (rows - 1), k = i - r * per;
      plan.set(c, {
        x: (k - (n - 1) / 2) * (tw + 13), y: (wide.length ? -54 : -110) + r * (th + 14), s: th / CARD_H,
      });
    });
    return plan;
  }
  /** [fill] puts cards into the row that are not there yet, once there are pictures of them. */
  async function finale(fill?: () => void): Promise<void> {
    const my = epoch;
    setPhase("gather");
    setAuto(false);
    await thumbs.ready;
    if (my === epoch) fill?.();
    await wait(calm ? 0 : 420);
    if (my !== epoch) return;
    // The empties are swept off the desk.
    snd.rustle(26, 620, 0.26, 0.7);
    for (const b of bags) {
      const to = { x: b.p.x + 420, y: b.p.y + rnd(-30, 60), rz: b.p.rz + rnd(20, 70) };
      void tween(b.p, to, 860, E.flow, rnd(0, 220));
    }
    void tween(box.p, { x: boxAway() }, 820, E.flow, 120);
    await wait(calm ? 0 : 560);
    if (my !== epoch) return;
    const plan = spreadPlan();
    for (const b of bags) b.state = "gone";
    // The plain ones first, then the rare, the rarest last.
    const turnOf = [...cards].sort((a, b) => RANK(a) - RANK(b)), plain = turnOf.filter((c) => !RANK(c)).length;
    const after = (c: Card) => {
      const i = turnOf.indexOf(c);
      return i < plain ? i * 30 : plain * 30 + 160 + (i - plain) * 170;
    };
    cards.forEach((c, i) => {
      const to = plan.get(c)!, late = after(c);
      c.state = "spread";
      c.home = { ...to };
      void tween(c.p, { x: to.x, s: to.s, rz: 0 }, 900, E.flow, late);
      void tween(c.p, { y: to.y }, 900, E.out, late);
      void wait(late + 620).then(() => {
        if (my !== epoch) return;
        snd.flip(0.32, 1.1 + i * 0.012, to.x / 480);
        c.gleam = -0.6;
        void tween(c, { gleam: 2 }, 520, E.out);
      });
    });
    await wait(after(turnOf[COUNT - 1]) + 940);
    if (my !== epoch) return;
    box.on = false;
    haste = 1;
    setPhase("end");
    emit({ type: "end" });
  }
  /** A card of the spread brought up close. */
  function tapEnd(x: number, y: number): void {
    for (const c of cards) {
      const w = (c.info.land ? CARD_H : CARD_W) * c.p.s / 2, h = (c.info.land ? CARD_W : CARD_H) * c.p.s / 2;
      if (Math.abs(x - c.p.x) < w && Math.abs(y - c.p.y) < h) return void takeUp(c);
    }
  }
  async function takeUp(c: Card): Promise<void> {
    setInspecting(c);
    setPhase("taking");
    const my = epoch;
    await Promise.all([kit.want(c.info, "front").ready, kit.want(c.info, "behind").ready]);
    if (my !== epoch || left || inspecting !== c) return;
    c.state = "inspect";
    shown = c;
    snd.slide(0.5, 1.1);
    scene.lights = PALE;
    void tween(scene, { spot: 0.82 }, 560, E.flow);
    await tween(c.p, { x: 0, y: -8, z: 120, s: c.info.land ? 1.6 : 1.28, rz: 0 }, 620, E.flow);
    setPhase("end");
  }
  async function putBack(): Promise<void> {
    const c = inspecting;
    if (!c || phase === "taking") return;
    setPhase("taking");
    setInspecting(null);
    shown = null;
    letTurnGo(c);
    snd.slide(0.4, 1.2);
    void tween(scene, { spot: 0 }, 560, E.flow);
    await tween(c.p, { x: c.home.x, y: c.home.y, z: 0, s: c.home.s, rx: 0, ry: 0 }, 620, E.flow);
    c.state = "spread";
    if (isPhase("taking")) setPhase("end");
  }

  /* ---------------------------------------------------------------- cut short */
  function skip(): "rush" | "all" | null {
    if (dead || left || phase === "gather" || phase === "end" || phase === "taking") return null;
    opened = COUNT;
    if (rushing || rushNext || calm || (phase !== "play" && phase !== "spot")) {
      spreadAll();
      return "all";
    }
    if (phase === "spot") rushNext = true;
    else void rush();
    return "rush";
  }

  /** What is left comes out of the box at once and stands in a row across the table. The bags of one member are torn
   * one after another from left to right, and their cards go down to the row, turning over on the way; then each rare one
   * is taken up out of the row, torn, and shown as it would have been, waiting for a press. A plain card that was out
   * already goes down first. */
  async function rush(): Promise<void> {
    epoch += 1;
    const my = epoch, live: Live = () => my === epoch;
    rushing = true;
    rushNext = false;
    pressWaiters = [];
    grip = null;
    eager = early = false;
    tempo = 0;
    haste = 1;
    shown = spinning = null;
    // A card out of its bag already goes on down.
    for (const b of bags) {
      const c = b.card;
      if (!b.torn || (c.state !== "in" && c.state !== "pop" && c.state !== "out")) continue;
      if (c.state === "out") {
        sendHome(c);
        continue;
      }
      if (c.state === "in") popCard(b);
      if (b.state !== "falling") {
        void tween(c.p, { y: -100, rz: 0 }, 300, E.flow);
        void dropBag(b, 1, 300);
      }
      void wait(300).then(() => { if (live()) sendHome(c); });
    }

    const row = bags.filter((b) => !b.torn && b.state !== "gone"), n = row.length;
    const plain = row.filter((b) => !RANK(b.card)), rare = row.filter((b) => RANK(b.card));
    // The first fronts come while the row comes out.
    for (const b of plain.slice(0, 3)) kit.want(b.card.info, "front");
    const s = n <= 6 ? 0.5 : n <= 10 ? 0.42 : 0.34, step = Math.min(BAG[0] * s + 14, 820 / Math.max(1, n - 1));
    let late = 0;
    if (n) {
      snd.slide(0.4, 0.8, -0.2);
      snd.rustle(8, 700, 0.12, 0.9);
      void tween(box.p, { rz: -0.9, y: 71 }, 160, E.flow).then(() => tween(box.p, { rz: 0, y: 74 }, 420, E.flow));
    }
    row.forEach((b, j) => {
      const to = [(j - (n - 1) / 2) * step, ROW_Y, 0];
      Object.assign(b, { row: true, hush: true, hint: -2, drive: null, alone: false, resolve: null });
      if (b === active) active = null;
      if (b.state === "box" || b.state === "rise") {
        // Up out of the box, one after another; one on its way up already goes on from where it is.
        const was = b.route;
        if (b.state === "box") Object.assign(b, { state: "rise", p: P() });
        const r = b.route = route(b, to, s, true);
        if (was) startAt(r, [b.p.x, b.p.y, b.p.z]);
        follow(b, r);
        b.px = b.p.x;
        b.py = b.p.y;
        void tween(r, { u: 1 }, RUSH_OUT, E.glide, late).then(() => { if (b.route === r) b.route = null; });
        late += RUSH_DEAL;
      } else {
        // One that is out already goes across.
        b.route = null;
        b.state = "line";
        void tween(b.p, { x: to[0], y: to[1], z: 0, rx: 0, ry: 0, rz: 0, s }, RUSH_OUT, E.flow);
      }
    });
    if (n) await wait(RUSH_OUT + Math.max(0, late - RUSH_DEAL));
    if (!live()) return;

    for (const [j, b] of plain.entries()) {
      // Their fronts are asked for a few ahead, and let go of once they are down.
      const ahead = plain.slice(j, j + 3).map((x) => x.card);
      ahead.forEach((c) => kit.want(c.info, "front"));
      const away = cards.filter((c) => c.state === "pop" || c.state === "fly");
      kit.letGo([...away, ...ahead, ...rare.slice(0, 1).map((x) => x.card)].map((c) => c.info));
      await kit.want(b.card.info, "front").ready;
      await kit.want(b.card.info, "behind").ready;
      if (!live()) return;
      void openInRow(b, live);
      await wait(RUSH_STEP);
      if (!live()) return;
    }

    for (const [j, b] of rare.entries()) {
      cur = b.i;
      kit.want(b.card.info, "front");
      kit.want(b.card.info, "behind");
      kit.letGo(rare.slice(j, j + 3).map((x) => x.card.info));
      // Taken up out of the row into the hand, as one that comes out of the box.
      Object.assign(b, { row: false, hush: false, state: "arrive" });
      active = b;
      snd.slide(0.26, 0.95, -0.35);
      await tween(b.p, { x: 0, y: 24, z: 0, rx: 0, ry: 0, rz: rnd(-1.0, 1.0), s: 1 }, RUSH_UP, E.glide);
      await kit.want(b.card.info, "front").ready;
      await kit.want(b.card.info, "behind").ready;
      if (!live() || active !== b) return;
      b.state = "sealed";
      grip = null;
      ptr.sx = ptr.x;
      ptr.sy = ptr.y;
      if (ptr.down) ptr.moved = 10;
      b.sealedAt = hc;
      if (!early) await wait(RUSH_BEAT);
      if (!live()) return;
      early = false;
      void tearAlone(b, 560);
      await new Promise<void>((done) => {
        b.resolve = done;
        if (b.torn) done();
      });
      if (!live()) return;
      if (b.card.info.land) await revealWide(b, live);
      else await revealSigned(b, live);
      if (!live()) return;
    }
    await finale();
  }
  /** A bag of the row is torn by itself, and its card comes up out of it and goes down to the row. */
  async function openInRow(b: Bag, live: Live): Promise<void> {
    const c = b.card;
    await tearAlone(b, RUSH_TEAR);
    if (!live()) return;
    // The flap goes up first.
    await wait(110);
    if (!live()) return;
    popCard(b);
    void tween(b, { open: 1 }, 260, E.flow);
    void tween(c.p, { y: c.p.y - CARD_H * 0.17 * b.p.s }, 200, E.out);
    await wait(150);
    if (!live()) return;
    void dropBag(b, 0.7, 360);
    sendHome(c);
  }
  /** A card that is out goes down to the row, in its turn. */
  function sendHome(c: Card): void {
    const k = cards.indexOf(c);
    bringHome(c, k);
    emit({ type: "kept", index: k });
  }
  /** [r] begins at [at] instead, straight on to where it clears the box. */
  function startAt(r: Route, at: number[]): void {
    r.pts[0] = at;
    const d = Math.hypot(...r.pts[1].map((v, k) => v - at[k])), more = d - r.at[1];
    r.at = r.at.map((v, k) => (k ? v + more : 0));
    r.clear = r.at[1];
    r.all = r.at[r.at.length - 1];
    r.u = 0;
  }

  /** Every card goes to the row from wherever it is, and the row is laid out. */
  function spreadAll(): void {
    rushNext = false;
    epoch += 1;
    time.clear();
    pressWaiters = [];
    grip = null;
    shown = null;
    spot = null;
    active = null;
    eager = early = false;
    haste = 1;
    tempo = 0;
    setAuto(false);
    setDim(false);
    void tween(scene, { spot: 0, toneAmt: 0, rays: 0 }, 760, E.flow);
    // The box goes to the side it leaves from.
    box.swaying = false;
    void tween(scene, { cover: 1, lensX: 0, lensY: 0 }, 500, E.flow);
    void tween(box.p, { x: boxAway(), y: 74, s: 0.52, ry: 15, rx: -19, rz: 0 }, 1100, E.flow);
    bags.forEach(clearAway);
    const my = epoch;
    cards.forEach((c, k) => {
      if (c.state === "pop") {
        // The bag is drawn off it first.
        void tween(c.p, { y: -100 }, 300, E.flow);
        void wait(300).then(() => { if (my === epoch) bringHome(c, k); });
      } else if (c.state !== "in" && c.state !== "rail") bringHome(c, k);
    });
    void finale(() => fillRow(cards));
  }
  /** A bag that is not on the heap leaves: one in the box with it, one on the table down over its edge. */
  function clearAway(b: Bag): void {
    const { route } = b;
    b.route = null;
    b.drive = null;
    b.resolve = null;
    if (b.state === "heap") return;
    if (b.state === "box" || b.state === "rise") {
      // One on its way up sinks back in.
      if (b.state === "rise" && route) b.rise = lerp(b.rise, 1.04, clamp(route.u * route.all / route.clear));
      b.state = "box";
      void tween(b, { rise: 0 }, 320, E.flow);
      return;
    }
    if (b.state !== "falling") b.p = heldPose(b);
    b.state = "falling";
    b.fade = 0;
    void tween(b, { fade: 1, beam: 0 }, 320, E.flow);
    const straight = b.card.state === "pop";
    void tween(b.p, { y: view.h / 2 + BAG[1], rz: b.p.rz + (straight ? 0 : rnd(-10, 10)) }, 620, E.flow)
      .then(() => { b.state = "gone"; });
  }
  /** A card that is out goes to its place in the row from wherever it is, written to the end. */
  function bringHome(c: Card, k: number): void {
    c.p.ry = ((c.p.ry + 180) % 360 + 360) % 360 - 180;
    if (c.signT >= 0 && c.signT < 1) void tween(c, { signT: 1.02 }, 320, E.flow);
    else c.signT = 2;
    void tween(c, { bend: 0, lipOn: 0, sheenAmt: 0 }, 260, E.flow);
    void collect(c, k);
  }
  /** Those of [list] not out of their bags come up into the row. */
  function fillRow(list: readonly Card[]): void {
    list.filter((c) => c.state === "in").forEach((c, i) => {
      const at = rowPose(c, cards.indexOf(c));
      c.state = "rail";
      c.signT = 2;
      c.p = { ...at, y: Math.max(at.y, view.h / 2) + 80 };
      void tween(c.p, { y: at.y }, 400, E.out, i * 8);
    });
  }
  function leave(): Promise<void> {
    return goWith(depart);
  }
  function goWith(way: () => Promise<void>): Promise<void> {
    left ??= new Promise((done) => {
      released = done;
      void way().then(done);
    });
    return left;
  }
  async function depart(): Promise<void> {
    // Called before the end, nothing else comes out.
    if (phase !== "end" && phase !== "taking") epoch += 1;
    setPhase("leaving");
    if (inspecting) await putBack();
    snd.slide(0.6, 0.9);
    cards.forEach((c, i) => void tween(c.p, { y: c.p.y - 620, rz: rnd(-6, 6) }, 720, E.flow, i * 12));
    await wait(900);
  }
  /** What the pointer had no more part in: the run is over, and the room as it was. */
  function breakOff(): void {
    epoch += 1;
    time.clear();
    pressWaiters = [];
    grip = null;
    spot = null;
    eager = early = false;
    haste = 1;
    tempo = 0;
    setAuto(false);
    setDim(false);
    void tween(scene, { spot: 0, toneAmt: 0, rays: 0 }, 420, E.flow);
  }
  /** Sends a bag back along [r], all the way down into the box however far up it stood there before. */
  function sinkAlong(b: Bag, r: Route, ms: number): void {
    const down = riseAt({ i: b.i, rise: 0 }), more = Math.hypot(...down.map((v, k) => v - r.pts[0][k]));
    r.u = (r.u * r.all + more) / (r.all + more);
    r.pts[0] = [...down];
    r.at = r.at.map((v, k) => (k ? v + more : 0));
    r.clear += more;
    r.all += more;
    r.back = true;
    b.route = r;
    void tween(r, { u: 0 }, ms, E.flow);
  }
  /** Another box on its way down to the shelf: the point its perspective is drawn toward, and where it lands. */
  let coming: { lens: Vec2; y: number } | null = null;
  async function departOut(place?: BoxPlace): Promise<void> {
    // A box skipped through goes out before it was all shown: what is on the desk goes with the cards.
    const midway = phase !== "end" && phase !== "taking";
    if (midway) breakOff();
    setPhase("leaving");
    if (inspecting) await putBack();
    snd.slide(0.6, 0.9);
    if (midway) sweep();
    // Gathered up by rows, the lowest first.
    const order = [...cards].sort((a, b) => b.p.y - a.p.y || a.p.x - b.p.x);
    order.forEach((c, i) => {
      void tween(c.p, { y: view.h / 2 + CARD_H * c.p.s, rz: rnd(-9, 9) }, 620, E.flow, i * 16);
      void tween(c.p, { x: c.p.x * 0.72 }, 620, E.flow, i * 16);
    });
    void tween(scene, { cover: 0, spot: 0 }, 760, E.flow, 380);
    const r = options.rect?.();
    if (!place || !r) return wait(1150);
    const k = place.css / view.css, { lid, tuck, flaps, lit, p } = place.box;
    const to = { ...p, x: p.x * k, y: p.y * k, z: p.z * k, s: p.s * k };
    const lens: Vec2 = [(place.cx - r.left - r.width / 2) / view.css, (place.cy - r.top - r.height / 2) / view.css];
    scene.coverAt = [lens[0] + to.x, lens[1] + to.y];
    await wait(420);
    if (midway) for (const b of bags) b.state = "gone";
    coming = { lens, y: to.y };
    Object.assign(box, { on: true, swaying: false, lid, tuck, flaps, lit, p: { ...to, y: to.y - view.h, ry: to.ry - 30 } });
    void tween(box.p, { ry: to.ry }, 840, E.out);
    void wait(420).then(() => snd.thud());
    await tween(box.p, { y: to.y }, 840, E.out);
    box.p = to;
  }
  /** The bags still about go off the desk, and the box off its side. */
  function sweep(): void {
    void tween(box.p, { x: boxAway() }, 520, E.flow);
    for (const b of bags) {
      b.route = null;
      b.drive = null;
      if (b.state === "gone") continue;
      if (b.state === "heap") void tween(b.p, { x: b.p.x + 420, rz: b.p.rz + 40 }, 520, E.flow, rnd(0, 120));
      else if (b.state === "box" || b.state === "rise") Object.assign(b, { state: "box", rise: 0 });
      else {
        if (b.state !== "falling") {
          b.p = heldPose(b);
          b.state = "falling";
          b.fade = 0;
          void tween(b, { fade: 1, beam: 0 }, 320, E.flow);
        }
        void tween(b.p, { y: view.h / 2 + BAG[1] }, 460, E.flow);
      }
    }
    if (active) active = null;
  }
  async function departBack(place?: BoxPlace): Promise<void> {
    const idle = phase === "intro";
    breakOff();
    setPhase("leaving");
    box.swaying = false;
    const r = options.rect?.(), held = active;
    active = null;
    shown = null;
    // A sealed bag goes back into the box the way it came.
    if (held && !held.torn) {
      const way = held.route ?? { ...route(held), u: 1, rz: held.p.rz };
      held.state = "arrive";
      held.drive = null;
      active = held;
      snd.slide(0.3, 1.05, -0.3);
      sinkAlong(held, way, 520);
    }
    // One that was on its way up goes down again.
    const rising = bags.find((b) => b.state === "rise" && b !== held);
    if (rising?.route) sinkAlong(rising, rising.route, 300);
    for (const b of bags) {
      if (b.state === "heap") void tween(b.p, { x: b.p.x + 420, rz: b.p.rz + 40 }, 520, E.flow, rnd(0, 120));
      else if (b.state === "box") void tween(b, { rise: 0 }, 320, E.flow);
      else if (b.state === "torn" || b.state === "falling") {
        if (b.state === "torn") {
          b.p = heldPose(b);
          b.state = "falling";
          b.fade = 0;
          void tween(b, { fade: 1, beam: 0 }, 320, E.flow);
        }
        b.route = null;
        void tween(b.p, { y: view.h / 2 + BAG[1] }, 460, E.flow);
      }
    }
    cards.forEach((c, i) => {
      if (c.state === "in") return;
      void tween(c.p, { y: view.h / 2 + CARD_H * Math.max(0.5, c.p.s), rz: c.p.rz + rnd(-6, 6) }, 460, E.flow, (i % 10) * 12);
    });
    if (!idle) await wait(held && !held.torn ? 500 : 280);
    if (dead) return;
    void tween(scene, { cover: 0 }, 820, E.flow, 60);
    if (!place || !r) {
      void tween(box.p, { x: -view.w, rz: -6 }, 700, E.flow);
      await wait(900);
      return;
    }
    const k = place.css / view.css, { x, y, z, rx, ry, rz, s } = place.box.p;
    const { lid, tuck, flaps, lit } = place.box;
    snd.slide(0.42, 0.8, -0.2);
    void tween(scene, {
      lensX: (place.cx - r.left - r.width / 2) / view.css, lensY: (place.cy - r.top - r.height / 2) / view.css,
    }, 900, E.flow);
    scene.coverAt = [(place.cx - r.left - r.width / 2) / view.css + x * k, (place.cy - r.top - r.height / 2) / view.css + y * k];
    void tween(box, { lid, tuck, flaps, lit }, 700, E.flow);
    await tween(box.p, { x: x * k, y: y * k, z: z * k, rx, ry: nearest(ry, box.p.ry), rz, s: s * k }, 900, E.flow);
  }
  /** The same angle, a whole turn or more away, nearest to [to]. */
  const nearest = (a: number, to: number) => a + Math.round((to - a) / 360) * 360;

  /* ---------------------------------------------------------------- each frame */
  function update(dt: number): void {
    wake();
    const step = dt * haste;
    time.advance(step);
    hc += step;
    const { clock } = time;
    if (!waiting()) stirred = clock;
    const want = clock - stirred < STIR_MS ? 1 : 0;
    ambRate += (want - ambRate) * (1 - Math.exp(-dt / 260));
    if (Math.abs(want - ambRate) < 0.002) ambRate = want;
    amb += step * ambRate;
    ptr.vx *= Math.exp(-dt / 90);
    ptr.vy *= Math.exp(-dt / 90);
    if (box.swaying) {
      const t = amb / 1000, k = box.sway;
      box.p.ry = box.ry0 + 7 * k * Math.sin(t * 0.8) + (ptr.inside ? ptr.x / 480 * 12 * k : 0);
      box.p.rx = box.rx0 + 2.5 * k * Math.sin(t * 0.63 + 1) + (ptr.inside ? -ptr.y / 320 * 5 * k : 0);
      // The lid stirs now and then.
      if (phase === "intro" && k && box.p.y > -20) box.lid = 90 + 5 * k * Math.max(0, Math.sin(hc / 1000 * LID_W)) ** 6;
    }
    for (const b of bags) {
      if (b.route) follow(b, b.route);
      if (b.state === "sealed" && b === active) {
        if (b.drive) pull(b, b.drive.q, 0.65);
        const idle = hc - b.sealedAt;
        if (b.state === "sealed" && !b.n && idle > 900 && !ptr.down) {
          const k = ((idle - 900) % 2100) / 900;
          b.hint = k < 1 ? -0.25 + k * 1.5 : -2;
        }
      }
      if (b.state === "line" && b.drive) pull(b, b.drive.q, 0.65);
      if (b.drive && b.torn) b.drive = null;
      // The flap rolls up as it comes away, and goes on over once it is free.
      b.curlV += ((b.torn ? 3.1 : 1.0 + 1.6 * clamp(b.q * 1.2)) - b.curl) * dt * (b.torn ? 0.00026 : 0.00011);
      b.curlV *= Math.exp(-dt / (b.torn ? 32 : 62));
      b.curl = clamp(b.curl + b.curlV * dt, 0.2, 3.12);
      b.rad += ((b.torn ? 0.02 : lerp(0.62, 0.36, b.q)) - b.rad) * (1 - Math.exp(-dt / (b.torn ? 80 : 140)));
      const want = b.state === "sealed" && ptr.down ? -b.strain * 2.2 : 0;
      b.tugV += (want - b.tug) * dt * 0.0016;
      b.tugV *= Math.exp(-dt / 55);
      b.tug += b.tugV * dt;
      // Soft film: it bows with the way it is moved and comes to rest with a small sway.
      const hx = (b.p.x - (b.px ?? b.p.x)) / Math.max(1, dt), hy = (b.p.y - (b.py ?? b.p.y)) / Math.max(1, dt);
      const loose = b.torn ? 1 : 0.45;
      b.px = b.p.x;
      b.py = b.p.y;
      const spring = (at: number, v: number, to: number) => v + ((to - at) * 0.00012 - v * 0.0075) * Math.min(dt, 32);
      b.vbx = spring(b.bx, b.vbx, clamp(hx * 15, -20, 20) * loose);
      b.bx += b.vbx * Math.min(dt, 32);
      b.vby = spring(b.by, b.vby, clamp(hy * 15, -20, 20) * loose);
      b.by += b.vby * Math.min(dt, 32);
      const inHand = b === active && b.state === "sealed" && ptr.down;
      const lifted = inHand ? 5 * b.q + 9 * b.strain * clamp(b.q * 8) : b.torn ? 0 : 3 * b.q;
      b.lift2 += (lifted - b.lift2) * (1 - Math.exp(-dt / 130));
      const rip = b.torn ? 3.2 : 2 + 2.4 * b.q + clamp(Math.abs(ptr.vy) * 1.2, 0, 2) * (inHand ? 1 : 0);
      b.vw += ((rip - b.wave) * 0.00010 - b.vw * 0.008) * Math.min(dt, 32);
      b.wave += b.vw * Math.min(dt, 32);
      b.shown += (b.q - b.shown) * (1 - Math.exp(-dt / 22));
      // The light swells behind the hand, and goes out once the bag is let go of.
      const held = b.state === "sealed" || b.state === "torn";
      const lit = held ? 0.18 * smooth(0, 0.1, b.q) + 0.82 * smooth(0.05, 1, b.q) : 0;
      b.glow += (lit - b.glow) * (1 - Math.exp(-dt / (lit > b.glow ? 90 : 190)));
    }
    {
      // While it is torn, the desk already goes a little dark and takes the colours.
      const a = active && (active.state === "sealed" || active.state === "torn") ? active : null;
      const k = 1 - Math.exp(-dt / 170);
      const { dusk, warm } = a ? glowOf(a.card.info) : { dusk: 0, warm: 0 };
      scene.dusk += ((a ? dusk * smooth(0.15, 1, a.glow) : 0) - scene.dusk) * k;
      scene.warm += ((a ? warm * 0.7 * smooth(0.1, 1, a.glow) : 0) - scene.warm) * k;
    }
    // The desk is lighter under light that lies over it; it comes up and goes down with that.
    scene.lift += (lifted() - scene.lift) * (1 - Math.exp(-dt / 90));
    if (Math.abs(lifted() - scene.lift) < 0.004) scene.lift = lifted();
    if (turn.card && !turn.held) {
      const settle = (k: "yaw" | "pitch", v: "vy" | "vp", to: number, ms: number) => {
        turn[v] += ((to - turn[k]) * 0.00006 - turn[v] * 0.0135) * ms;
        turn[k] += turn[v] * ms;
      };
      for (let rest = dt; rest > 0; rest -= 8) {
        settle("yaw", "vy", turn.to, Math.min(8, rest));
        settle("pitch", "vp", 0, Math.min(8, rest));
      }
    }
    // Cards and the bag in hand lean toward the pointer.
    for (const c of cards) {
      const held = c === shown || (spot?.sign && c === spot.card);
      const near = held && !turn.held, wide = c === inspecting;
      const tx = near && ptr.inside ? clamp(ptr.x / 300, -1, 1) : near ? 0.5 * Math.sin(amb / 1300) : 0;
      const ty = near && ptr.inside ? clamp((ptr.y - c.p.y) / 260, -1, 1) : near ? 0.5 * Math.sin(amb / 1700 + 1) : 0;
      const k = 1 - Math.exp(-dt / 90);
      c.amp += ((wide ? 26 : 18) - c.amp) * k;
      movePen(c, dt);
      c.float += ((held ? 1 : 0) - c.float) * (1 - Math.exp(-dt / 400));
      c.tiltX += (tx - c.tiltX) * k;
      c.tiltY += (ty - c.tiltY) * k;
    }
    if (active) {
      // One on its way back stands straight by the time it is over the box.
      const a: Bag = active, back = !!a.route?.back, on = !back && (a.state === "sealed" || a.state === "arrive");
      const k = 1 - Math.exp(-dt / (back ? 70 : 160));
      const toX = on && ptr.inside ? clamp(ptr.x / 260, -1, 1) : on ? 0.55 * Math.sin(amb / 1500) : 0;
      const toY = on && ptr.inside ? clamp(ptr.y / 260, -1, 1) : on ? 0.4 * Math.sin(amb / 1900 + 2) : 0;
      a.float += ((on ? 1 : 0) - a.float) * (1 - Math.exp(-dt / (back ? 70 : 400)));
      a.leanX += (toX - a.leanX) * k;
      a.leanY += (toY - a.leanY) * k;
    }
    fx = fx.filter((f) => {
      f.life += dt;
      if (f.life < 0) return true;
      f.vy += f.g * dt;
      const k = Math.exp(-dt * f.drag);
      f.vx *= k;
      f.vy *= f.kind ? k : 1;
      f.x += f.vx * dt;
      f.y += f.vy * dt;
      f.spin += f.vs * dt * 10;
      return f.life < f.max;
    });
    rest();
  }

  /** The run waits for a hand (a press, or a sealed bag to tear), with nothing on the timeline. What it waits for
   * otherwise (the pictures of a card) comes outside the frames, and is drawn for until it is there. */
  const waiting = () => (phase === "intro" || phase === "play" || phase === "spot") && !time.busy && !ptr.down
    && (pressWaiters.length > 0 || active?.state === "sealed");
  /** Everything drawn that moves from one picture to the next without the timeline. */
  function looks(): number[] {
    const v = [amb, box.p.x, box.p.y, box.p.rx, box.p.ry, box.p.rz, box.lid, scene.dusk, scene.warm, scene.lift];
    v.push(turn.yaw, turn.pitch);
    for (const b of bags) {
      if (b.state === "gone") continue;
      v.push(b.p.x, b.p.y, b.p.z, b.p.rx, b.p.ry, b.p.rz, b.p.s, b.bx, b.by, b.curl, b.rad, b.tug, b.lift2, b.wave);
      v.push(b.shown, b.glow, b.hint, b.float, b.leanX, b.leanY);
    }
    for (const c of cards) {
      if (c.state === "in") continue;
      v.push(c.p.x, c.p.y, c.p.z, c.p.rx, c.p.ry, c.p.rz, c.p.s, c.tiltX, c.tiltY, c.float, c.amp, c.tipAmt);
    }
    return v;
  }
  /** Whether the picture just drawn is the one the next would be; if so, a wake-up is set for the next hint. */
  function rest(): void {
    const now = looks(), before = seen;
    seen = now;
    if (!waiting() || ambRate || fx.length || now.length !== before.length) return;
    for (let k = 0; k < now.length; k++) if (Math.abs(now[k] - before[k]) > STILL_EPS) return;
    still = true;
    const ms = nextHint();
    if (!Number.isFinite(ms)) return;
    nap = setTimeout(() => {
      nap = null;
      if (dead || !still) return;
      // Nothing was drawn meanwhile: the hints go on from where the next one begins.
      hc += ms;
      still = false;
      emit({ type: "stir" });
    }, ms);
  }
  /** A picture is wanted: of a touch, or of a frame drawn. */
  function wake(): void {
    still = false;
    if (nap !== null) clearTimeout(nap);
    nap = null;
  }
  function touched(): void {
    wake();
    stirred = time.clock;
  }
  /** How long until a hint plays again, by the hints' clock. */
  function nextHint(): number {
    let ms = Infinity;
    if (box.swaying && phase === "intro" && box.sway && box.p.y > -20) {
      const at = ((hc / 1000) * LID_W) % (2 * Math.PI);
      // Just begun to rise, too little to be seen yet: it goes on now.
      ms = at > LID_FROM && at < Math.PI / 2 ? 0
        : (((LID_FROM - at) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI)) / LID_W * 1000;
    }
    const a = active;
    if (a?.state === "sealed" && !a.n && !ptr.down) {
      const idle = hc - a.sealedAt;
      ms = Math.min(ms, idle < 900 ? 900 - idle : 2100 - ((idle - 900) % 2100));
    }
    return Math.max(1, ms);
  }
  /* ---------------------------------------------------------------- drawing */
  /** A bag in hand gives under the pull, floats, and leans toward the pointer. */
  const heldPose = (b: Bag): Pose => ({
    ...b.p, y: b.p.y + b.tug + 2.6 * Math.sin(amb / 1050) * b.float, ry: b.p.ry + b.leanX * 13,
    rx: b.p.rx - b.leanY * 11,
  });
  const lamp = (): Vec3 => [
    ptr.inside ? ptr.x : 180 * Math.sin(amb / 1400),
    ptr.inside ? ptr.y : -120 + 60 * Math.sin(amb / 1900), 230,
  ];
  const roomShift = (): Vec2 => [
    (ptr.inside ? ptr.x / 480 : 0.4 * Math.sin(amb / 2300)) * 0.05,
    (ptr.inside ? ptr.y / 320 : 0.3 * Math.sin(amb / 2900)) * 0.035,
  ];
  function draw(): void {
    // What the painter moves by itself (a bag's breath, a card held up, the light and the desk) stands with the rest.
    const clock = amb, { clearDepth, shadow, solid } = painter;
    gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
    gl.enable(gl.BLEND);
    gl.depthFunc(gl.LEQUAL);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const frame = { vp: G.camera(view.w, view.h), px: view.px, clock, lamp: lamp(), room: roomShift() };
    painter.begin(frame);
    const dark = Math.max(scene.spot, scene.dusk), { cover } = scene;
    // The desk was drawn over the cleared colour with whatever blending the picture before ended with.
    if (cover > 0) {
      const tone = Math.max(scene.toneAmt, scene.warm);
      painter.desk(view.w, view.h, dark, tone, scene.lights, scene.lift, cover, scene.coverAt, art.id);
    }
    const dim = 1 - 0.72 * dark, inDark = 1 - 0.52 * dark;
    if (scene.lensX || scene.lensY) painter.begin({ ...frame, vp: G.lens(view.w, view.h, scene.lensX, scene.lensY) });

    // The heap of empties.
    for (const b of bags) {
      if (b.state === "heap") shadow(b.p.x + 5, b.p.y + 8, BAG[0] * b.p.s, BAG[1] * b.p.s, b.p.rz, 0.30 * dim);
    }
    for (const b of bags) {
      if (b.state !== "heap") continue;
      const lit = dim * 0.9;
      solid();
      clearDepth();
      painter.foil(b, b.p, 1, { lit });
      painter.foil(b, b.p, 3, { low: true, lit });
      clearDepth();
      painter.foil(b, b.p, 2, { low: true, lit });
    }

    // The box, and the bags while they are in it or coming out of it.
    if (box.on) {
      const s = box.p.s;
      const shY = box.p.y + BOX[1] * s * 0.5 - 4;
      const lift = clamp((box.p.y + 6) / -700);
      if (coming) {
        painter.begin({ ...frame, vp: G.lens(view.w, view.h, ...coming.lens) });
        const near = clamp(1 - (coming.y - box.p.y) / 220);
        groundShade(painter, { ...box, p: { ...box.p, y: coming.y } }, (1 - cover) * near * near);
      } else {
        shadow(
          box.p.x + 6, shY, BOX[0] * s * (1.15 + 0.3 * lift), BOX[2] * s * 0.8, 0,
          (0.55 - 0.45 * lift) * dim * (phase === "intro" ? 1 : 0.8) * cover, phase === "intro" ? 1.9 : 1.5,
        );
        // On paper its shade is the shelf's (shelf.ts).
        if (cover < 1) groundShade(painter, box, 1 - cover);
      }
      solid();
      clearDepth();
      painter.box(box, box.lit * dim, "back");
      const rising = bags.filter((b) => b.state === "rise" || (b.state === "box" && box.lid > 100));
      for (const b of rising) {
        const at = riseAt(b);
        const p = b.route ? b.p : P(at[0], at[1], { z: at[2], rx: box.p.rx, ry: box.p.ry, s: box.p.s });
        painter.foil(b, p, 0, { low: true, lit: dim });
      }
      painter.box(box, box.lit * dim, "front");
      if (coming) painter.begin(frame);
    }

    // What has been opened, along the bottom or laid out.
    for (const c of cards) {
      if (!thumbs.drawn || (c.state !== "rail" && c.state !== "spread")) continue;
      const w = (c.info.land ? CARD_H : CARD_W) * c.p.s, h = (c.info.land ? CARD_W : CARD_H) * c.p.s;
      shadow(c.p.x + 3, c.p.y + 6, w, h, c.p.rz, 0.34 * dim, 1.5);
      painter.thumb(c, dim);
    }

    // What was left of a box skipped through, standing in a row.
    for (const b of bags) {
      if (!b.row || (b.state !== "line" && b.state !== "torn")) continue;
      const c = b.card, p = b.p;
      shadow(p.x + 6, p.y + 16 * p.s, BAG[0] * p.s, BAG[1] * p.s, p.rz, 0.45 * dim, 1.55);
      solid();
      clearDepth();
      const between = c.state === "pop" ? () => {
        c.lip = p.y - (BAG[1] / 2 - 10) * p.s;
        c.lipLight = b.beam * glowOf(c.info).power;
        drawCard(c);
      } : null;
      painter.bag(b, { between, lit: dim });
    }

    // A bag on its way to the heap.
    for (const b of bags) {
      if (b.state !== "falling") continue;
      const c = b.card;
      const between = c.state === "pop" ? () => {
        c.lip = b.p.y - BAG[1] / 2 + 10;
        c.lipLight = b.beam * glowOf(c.info).power;
        drawCard(c);
      } : null;
      solid();
      clearDepth();
      painter.bag(b, { between, lit: lerp(inDark, dim, b.fade) });
    }

    // The bag in hand.
    if (active && active.state !== "falling" && active.state !== "heap" && active.state !== "rise") {
      const b: Bag = active, p = heldPose(b);
      shadow(p.x + 10 - b.leanX * 12, p.y + 26, BAG[0] * p.s, BAG[1] * p.s, p.rz, 0.5, 1.55);
      solid();
      clearDepth();
      const c = b.card;
      const between = c.state === "pop" ? () => {
        c.lip = p.y - BAG[1] / 2 + 10;
        c.lipLight = b.beam * glowOf(c.info).power;
        drawCard(c);
      } : null;
      painter.bag(b, { p, between, lit: inDark });
    }

    // Light for a card that earned it.
    if (scene.rays > 0.01) painter.rays(scene.rayAt.x, scene.rayAt.y, scene.rays, scene.lights);
    // The burst lies behind the card, and over it for a blink only.
    painter.wash(view.w, view.h, scene.flashTone, scene.flash * 0.7);
    for (const c of cards) {
      if (c.state !== "out" && c.state !== "fly" && c.state !== "inspect") continue;
      const w = (c.info.land ? CARD_H : CARD_W) * c.p.s, h = (c.info.land ? CARD_W : CARD_H) * c.p.s;
      const turned = Math.abs(Math.cos(c.p.ry * RAD)), open = Math.abs(Math.cos(c.p.rx * RAD));
      shadow(
        c.p.x + 8 - c.tiltX * 10, c.p.y + 24, w * (0.35 + 0.65 * turned), h * (0.2 + 0.8 * open), c.p.rz,
        0.5 * (1 - 0.4 * dark), 1.55,
      );
      solid();
      clearDepth();
      drawCard(c);
    }
    painter.bits(fx, true);
    painter.wash(view.w, view.h, scene.flashTone, scene.flash ** 4 * 0.85);
    ended = painter.blended;
  }
  /** The blending the last picture ended with. */
  let ended: Blend = "over";
  const lifted = () => (ended === "add" ? 1 : 0);
  const drawCard = (c: Card) => painter.card(c, c.p, turn.card === c ? turn : null);

  /* ---------------------------------------------------------------- what the host holds */
  snd.load();
  void kit.load(art.id);
  const thumbs = kit.thumbs(art.id);
  if (FROM && !calm) layOut(FROM);
  void run();
  queueMicrotask(() => {
    const first = untold ?? [];
    untold = null;
    first.forEach(emit);
  });

  return {
    resize(cssW, cssH, dpr) {
      const css = Math.min(cssW / STAGE_W, cssH / STAGE_H);
      view = { w: cssW / css, h: cssH / css, px: css * dpr, css };
      if (from) putFrom(from);
      from = null;
    },
    down(x, y, t) { if (!dead && !left) { touched(); onDown(x, y, t); } },
    move(x, y, t) { if (!dead) { touched(); onMove(x, y, t); } },
    up(off = false) { if (!dead) { touched(); onUp(off); } },
    leavePointer() { if (!ptr.down) { touched(); ptr.inside = false; } },
    press(repeat = false) { if (!dead && !left) { touched(); press(repeat); } },
    setAuto(on) { if (!dead && !left) { touched(); setAuto(on); } },
    skip() { touched(); return skip(); },
    leave() { touched(); return leave(); },
    goOut: (place) => { touched(); return goWith(() => departOut(place)); },
    goBack: (place) => { touched(); return goWith(() => departBack(place)); },
    places: () => cards.map((c, index) => ({
      index, x: c.home.x, y: c.home.y, w: (c.info.land ? CARD_H : CARD_W) * c.home.s, h: (c.info.land ? CARD_W : CARD_H) * c.home.s,
    })),
    update(dt) { if (!dead) update(dt); },
    draw() { if (!dead) draw(); },
    state: () => ({
      phase, cur, opened,
      active: active && { i: active.i, state: active.state, q: active.q, n: active.n, card: active.card.info.id },
      shown: shown?.info.id, spot: spot?.card.info.id ?? null, tempo, fx: fx.length, deal: cards.map((c) => c.info.id),
      get err() { return gl.getError(); },
    }),
    get clock() { return time.clock; },
    get busy() {
      if (dead) return false;
      // Bags and the box are still only once the table has stood waiting a while.
      if (phase !== "end" && phase !== "leaving") return !still;
      return time.busy || !!inspecting || fx.length > 0 || scene.lift !== lifted();
    },
    dispose(followed = false) {
      if (dead) return;
      dead = true;
      wake();
      epoch += 1;
      time.clear();
      pressWaiters = [];
      fx = [];
      kit.letGo([], 0, !followed);
      released?.();
    },
  };
}
