// A photocard looked at on its own: it comes out of its small picture, leans after the pointer, is turned over by hand,
// and a signed one can be signed again. It lies on paper, so the canvas is clear around it.
import type { CardInfo, SeriesArt } from "./art";
import type { Scene } from "./engine";
import { lens, P, type GL, type Pose } from "./gl";
import type { Kit } from "./kit";
import { clamp, RAD } from "./math";
import { CARD_H, CARD_W, cardModel, PLUM, STAGE_H, STAGE_W, type CardModel, type Painter } from "./painter";
import { movePen } from "./pen";
import type { CardPlace } from "./place";
import type { Face } from "./shelf";
import { createTimeline, E } from "./time";
import { dragTurn, dropTurn, settleTurn, still, turned } from "./turn";

export interface ViewerSound {
  slide(amount: number, rate: number, pan?: number): void;
  flip(amount: number, rate: number, pan?: number): void;
}
export interface ViewerOptions {
  art: SeriesArt;
  calm?: boolean;
  sound?: ViewerSound;
  /** The host on the screen. */
  rect(): DOMRect;
}
export interface Viewer extends Scene {
  /** CSS pixels on the right that belong to what stands beside the card. */
  inset(px: number): void;
  /** The first card; it comes out of [from], and is signed as it opens with [write]. [near]: the cards beside it in
   *  the list, whose textures are kept while they are there. */
  open(face: Face, o?: { from?: CardPlace; write?: boolean; near?: readonly Face[] }): void;
  /** Another card comes in from the left (-1) or the right; 0 for the other face of the same one. */
  change(face: Face, dir: -1 | 0 | 1, near?: readonly Face[]): void;
  turnOver(): void;
  /** Writes the signature again. */
  write(): void;
  /** Back to where it came from; resolves once it is there. */
  close(): Promise<void>;
  down(x: number, y: number, t: number): void;
  move(x: number, y: number, t: number): void;
  /** "beside" for a press that was not on the card; null for one that was taken away ([off]). */
  up(off?: boolean): "card" | "beside" | null;
  leavePointer(): void;
  dispose(): void;
}

/** It sways for this long after the pointer was last here. */
const AWAKE_MS = 20_000, DROWSE_MS = 2600;
const TAP = 6;

interface Shown {
  face: Face; model: CardModel; p: Pose; turn: ReturnType<typeof turned>; shade: number;
  /** How big it is once it lies there. */
  s: number;
}

export function createViewer(gl: GL, kit: Kit, painter: Painter, opts: ViewerOptions): Viewer {
  const { art, calm = false, sound, rect } = opts;
  const time = createTimeline();
  let dead = false;
  let round = 0;
  let aside = 0;
  let view = { w: STAGE_W, h: STAGE_H, px: 1, css: 1 };
  let card: Shown | null = null;
  /** Those before, on their way out. */
  let gone: Shown[] = [];
  let from: { face: Face; place: CardPlace } | null = null;
  let closing = false;
  let woken = 0;
  let settled = false;
  /** Cards whose textures are being loaded: they are shown once those are there. */
  let loading = 0;
  /** The card asked for last, and those beside it in the list. */
  let wanted: Face | null = null;
  let beside: readonly Face[] = [];

  const infoOf = (f: Face): CardInfo | undefined => (f.signed ? art.signed(f.card) : art.card(f.card));
  /** How big a card lies there: what fits beside the facts, with room for the keys on either side. */
  function size(info: CardInfo): number {
    const w = info.land ? CARD_H : CARD_W, h = info.land ? CARD_W : CARD_H;
    return Math.min(1.78, (view.h - 92) / h, (view.w - aside / view.css - 132) / w);
  }
  const make = (face: Face): Shown => {
    const info = infoOf(face)!, s = size(info);
    return { face, model: { ...cardModel(info), amp: 24, signT: 2 }, p: P(0, 0, { s }), turn: turned(), shade: 1, s };
  };
  function refit(): void {
    if (!card || closing) return;
    const s = size(card.model.info);
    if (s === card.s) return;
    card.s = s;
    if (time.busy) void time.tween(card.p, { s }, 240, E.flow);
    else card.p.s = s;
  }
  /** Lets go of the full-size textures of every card but the one on show, those on their way out, the one asked for last
   *  and those beside it. */
  function recycle(): void {
    if (dead) return;
    const keep = [card?.face, ...gone.map((g) => g.face), wanted, ...beside].flatMap((f) => (f ? [infoOf(f)!] : []));
    kit.letGo(keep, 0, true);
  }
  async function load(face: Face): Promise<void> {
    const info = infoOf(face)!;
    loading++;
    await Promise.all([kit.signs(art.id), kit.want(info, "front").ready, kit.want(info, "behind").ready])
      .finally(() => { loading--; });
  }
  /** A place on the screen, as a pose of [info] here. */
  function poseAt(place: CardPlace, info: CardInfo): Pose {
    const r = rect(), k = view.css;
    return P((place.x - r.left - r.width / 2 + aside / 2) / k, (place.y - r.top - r.height / 2) / k, {
      rz: place.rz, s: place.w / k / (info.land ? CARD_H : CARD_W),
    });
  }
  function gleam(c: CardModel): void {
    c.sheen = -0.6;
    c.sheenAmt = 0.24;
    void time.tween(c, { sheen: 1.9 }, 1200, E.flow, 220);
  }

  function open(
    face: Face, { from: place, write: pen = false, near = [] }: { from?: CardPlace; write?: boolean; near?: readonly Face[] } = {},
  ): void {
    const mine = ++round;
    woken = time.clock;
    wanted = face;
    beside = near;
    void load(face).then(() => {
      if (dead) return;
      // Another was asked for meanwhile: this one's textures may have come after it.
      if (mine !== round) return recycle();
      const c = make(face), to = { ...c.p };
      card = c;
      if (pen) c.model.signT = -1;
      from = place ? { face, place } : null;
      if (!calm) {
        Object.assign(c.p, place ? poseAt(place, c.model.info) : P(0, 70, { s: to.s * 0.9, rz: -3 }));
        c.shade = 0.3;
        sound?.slide(0.36, 1.1);
        void time.tween(c.p, { x: 0, y: 0, s: to.s, rz: 0 }, 640, E.flow);
        void time.tween(c.p, { z: 90, ry: -16 }, 300, E.flow)
          .then(() => { if (mine === round) void time.tween(c.p, { z: 0, ry: 0 }, 520, E.flow); });
        void time.tween(c, { shade: 1 }, 640, E.flow);
        gleam(c.model);
      }
      if (pen) void time.wait(calm ? 0 : 620).then(() => { if (mine === round) write(); });
    });
  }
  function change(face: Face, dir: -1 | 0 | 1, near: readonly Face[] = []): void {
    const mine = ++round;
    woken = time.clock;
    wanted = face;
    beside = near;
    void load(face).then(async () => {
      if (dead) return;
      if (mine !== round) return recycle();
      const was = card;
      if (!was || calm) {
        card = make(face);
        recycle();
        return;
      }
      if (!dir) {
        // Turned over once, on from how it is seen: the other face comes round.
        sound?.flip(0.5, 1);
        const seen = ((was.p.ry + was.turn.yaw) % 360 + 530) % 360 - 170, half = seen < -90 ? -180 : 180;
        was.p = { ...was.p, ry: seen };
        Object.assign(was.turn, { yaw: 0, to: 0, vy: 0, held: false });
        void time.tween(was.p, { x: 0, y: 0, z: 110, rz: 0, s: was.s }, 300, E.flow);
        await time.tween(was.p, { ry: half }, 330 * Math.abs(half - seen) / 180, (t) => t * t * (2 - t));
        if (dead || mine !== round) return;
        const c = make(face);
        c.p = { ...was.p, ry: -half };
        c.turn = was.turn;
        c.model.tiltX = was.model.tiltX;
        c.model.tiltY = was.model.tiltY;
        card = c;
        void time.tween(c.p, { x: 0, y: 0, z: 0, rz: 0, ry: 0, s: c.s }, 560, E.out);
        gleam(c.model);
        return;
      }
      sound?.slide(0.34, 1.15, dir * 0.3);
      gone.push(was);
      void time.tween(was.p, { x: -dir * (view.w * 0.5 + 180), rz: -dir * 7, ry: was.p.ry + dir * 18 }, 420, E.flow)
        .then(() => {
          gone = gone.filter((g) => g !== was);
          recycle();
        });
      const c = make(face), to = { ...c.p };
      Object.assign(c.p, { x: dir * (view.w * 0.5 + 160), rz: dir * 7, ry: -dir * 18 });
      card = c;
      void time.tween(c.p, { x: 0, rz: 0, ry: 0, s: to.s }, 560, E.out, 40);
      gleam(c.model);
    });
  }
  /** Counts the times it was begun to write. */
  let pens = 0;
  function write(): void {
    const c = card, sign = c?.model.info.signed;
    if (!c || !sign) return;
    woken = time.clock;
    // It is written on its face.
    if (Math.abs(((c.turn.to % 360) + 360) % 360 - 180) < 90) c.turn.to += 180;
    if (calm) { c.model.signT = 2; return; }
    const mine = ++pens;
    // The pen may still be on it from the time before.
    void time.tween(c.model, { signT: 0, gleamInk: -1 }, 1).then(() => {
      if (mine === pens) return time.tween(c.model, { signT: 1.02 }, sign.ms * 1.02, E.linear);
    }).then(() => {
      if (card !== c || mine !== pens) return;
      c.model.signT = 2;
      c.model.gleamInk = -0.5;
      void time.tween(c.model, { gleamInk: 1.9 }, 1150, E.flow, 80);
    });
  }
  async function close(): Promise<void> {
    round++;
    closing = true;
    const c = card;
    if (!c || calm) return;
    sound?.slide(0.3, 1.2);
    c.turn.to = Math.round(c.turn.yaw / 360) * 360;
    const home = from && from.face.card === c.face.card && from.face.signed === c.face.signed ? poseAt(from.place, c.model.info) : null;
    void time.tween(c, { shade: home ? 0.25 : 0 }, 320, E.flow);
    if (home) await time.tween(c.p, { x: home.x, y: home.y, s: home.s, rz: home.rz, z: 0, ry: 0 }, 420, E.flow);
    else await time.tween(c.p, { y: 60, s: c.p.s * 0.94, ry: 0 }, 260, E.flow);
  }

  /* ---------------------------------------------------------------- pointer */
  const ptr = { x: 0, y: 0, vx: 0, vy: 0, t: 0, inside: false, down: false, moved: 0, on: false };
  function place(clientX: number, clientY: number): [number, number] {
    const r = rect();
    return [(clientX - r.left - r.width / 2 + aside / 2) / view.css, (clientY - r.top - r.height / 2) / view.css];
  }
  function onCard(x: number, y: number): boolean {
    if (!card) return false;
    const { p, model: { info } } = card;
    return Math.abs(x - p.x) < (info.land ? CARD_H : CARD_W) * p.s / 2 && Math.abs(y - p.y) < (info.land ? CARD_W : CARD_H) * p.s / 2;
  }

  function update(dt: number): void {
    time.advance(dt);
    ptr.vx *= Math.exp(-dt / 90);
    ptr.vy *= Math.exp(-dt / 90);
    const t = time.clock, sway = calm ? 0 : clamp(1 - (t - woken - AWAKE_MS) / DROWSE_MS);
    settled = true;
    for (const c of [card, ...gone]) {
      if (!c) continue;
      const near = c === card && ptr.inside && !ptr.down && !calm && !closing;
      const tx = near ? clamp(ptr.x / 300, -1, 1) : closing ? 0 : 0.45 * Math.sin(t / 1300) * sway;
      const ty = near ? clamp(ptr.y / 260, -1, 1) : closing ? 0 : 0.4 * Math.sin(t / 1700 + 1) * sway;
      const k = 1 - Math.exp(-dt / 90), m = c.model;
      if (Math.abs(tx - m.tiltX) + Math.abs(ty - m.tiltY) > 0.004) settled = false;
      m.tiltX += (tx - m.tiltX) * k;
      m.tiltY += (ty - m.tiltY) * k;
      settleTurn(c.turn, dt);
      if (!still(c.turn)) settled = false;
      movePen(m, dt);
      if (m.tipAmt > 0.01) settled = false;
    }
    if (sway > 0 && !closing) settled = false;
  }
  function draw(): void {
    gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
    gl.enable(gl.BLEND);
    gl.depthFunc(gl.LEQUAL);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    painter.begin({
      vp: lens(view.w, view.h, -aside / 2 / view.css, 0), px: view.px, clock: time.clock,
      lamp: [ptr.inside ? ptr.x : -120, ptr.inside ? ptr.y : -160, 230], room: [0, 0],
    });
    for (const c of [...gone, card]) {
      if (!c) continue;
      const { p, model: m } = c;
      const w = (m.info.land ? CARD_H : CARD_W) * p.s, h = (m.info.land ? CARD_W : CARD_H) * p.s;
      const yaw = (p.ry + c.turn.yaw + m.tiltX * m.amp) * RAD, pitch = (p.rx + c.turn.pitch) * RAD;
      const wide = 0.35 + 0.65 * Math.abs(Math.cos(yaw)), tall = 0.3 + 0.7 * Math.abs(Math.cos(pitch));
      // Two shadows: one close under it, one wide and faint.
      painter.shadow(p.x + 5 - m.tiltX * 8, p.y + 12, w * wide, h * tall, p.rz, 0.30 * c.shade, 1.12, PLUM);
      painter.shadow(p.x + 8 - m.tiltX * 14, p.y + 26, w * wide, h * tall, p.rz, 0.20 * c.shade, 1.34, PLUM);
      painter.solid();
      painter.clearDepth();
      painter.card(m, p, c.turn);
    }
  }

  return {
    open, change, write, close, update, draw,
    get busy() { return loading > 0 || time.busy || ptr.down || !settled; },
    inset(px) {
      aside = px;
      refit();
    },
    resize(w, h, dpr) {
      const css = Math.min(w / STAGE_W, h / STAGE_H);
      view = { w: w / css, h: h / css, px: css * dpr, css };
      refit();
    },
    turnOver() {
      if (!card) return;
      woken = time.clock;
      sound?.flip(0.5, 1);
      card.turn.to += 180;
      if (calm) card.turn.yaw = card.turn.to;
    },
    move(cx, cy, t) {
      const [x, y] = place(cx, cy);
      const dt = Math.max(1, t - (ptr.t || t - 16)), dx = x - ptr.x, dy = y - ptr.y, k = 1 - Math.exp(-dt / 40);
      ptr.t = t;
      ptr.vx += (dx / dt - ptr.vx) * k;
      ptr.vy += (dy / dt - ptr.vy) * k;
      ptr.x = x;
      ptr.y = y;
      ptr.inside = true;
      woken = time.clock;
      if (!ptr.down) return;
      ptr.moved += Math.hypot(dx, dy);
      if (card?.turn.held) dragTurn(card.turn, dx, dy);
    },
    down(cx, cy, t) {
      const [x, y] = place(cx, cy);
      Object.assign(ptr, { x, y, t, vx: 0, vy: 0, down: true, moved: 0, inside: true, on: onCard(x, y) });
      woken = time.clock;
      if (card && !closing) Object.assign(card.turn, { held: true, vy: 0, vp: 0 });
    },
    up(off = false) {
      if (!ptr.down) return null;
      ptr.down = false;
      woken = time.clock;
      const tap = ptr.moved < TAP;
      if (card) {
        if (tap) card.turn.held = false;
        else dropTurn(card.turn, ptr.vx, ptr.vy);
      }
      if (!tap || off) return null;
      return ptr.on ? "card" : "beside";
    },
    leavePointer() { if (!ptr.down) ptr.inside = false; },
    dispose() {
      dead = true;
      round++;
      time.clear();
      kit.letGo([], 0, true);
    },
  };
}
