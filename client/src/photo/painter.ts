// Draws the things of a photocard scene: the desk, the box, silver bags, cards, light. A view sets the frame and asks
// for its things from back to front; each is drawn from its model alone, so several views share one painter.
// Bags, boxes and cards come after solid() and a cleared depth. Flat things turn the depth test off by themselves.
import { seriesArt, type CardInfo } from "./art";
import * as G from "./gl";
import { P, type GL, type Mat4, type Pose, type Program, type Uniforms, type Vec2, type Vec3, type Vec4 } from "./gl";
import type { Kit } from "./kit";
import { clamp, lerp, RAD, smooth } from "./math";

/** What fits the middle of every window. */
export const STAGE_W = 960, STAGE_H = 640;
/** Millimetres of the real things, and the size they have in the middle of the stage. */
export const MM = 400 / 97;
/** A bag's body, and the flap folded over it. */
export const BAG: Vec2 = [62 * MM, 90 * MM], FLAP = 18 * MM;
export const CARD_W = 54 * MM, CARD_H = 86 * MM;
export const BOX: Vec3 = [73.5 * MM, 100 * MM, 38 * MM];
const BOARD = 1.4 * MM;
/** A card's thickness. */
const THICK = 1.0 * MM;
/** How far round a fold in the board goes. */
const FOLD = 1.7 * MM;
const BLACK: Vec3 = [0, 0, 0];
/** What shades paper. */
export const PLUM: Vec3 = [0.22, 0.12, 0.30];
const NONE: Vec4 = [0, 0, 0, 0];
const SILVER: { dark: Vec3; lit: Vec3 } = { dark: [0.36, 0.33, 0.37], lit: [1.0, 0.98, 0.97] };

/** What a whole picture is drawn with. */
export interface Frame {
  /** World to clip (camera()). */
  vp: Mat4;
  /** Device pixels to a design unit. */
  px: number;
  /** Milliseconds, for what breathes and drifts. */
  clock: number;
  /** A small lamp, in design units: the pointer, or something that wanders. */
  lamp: Vec3;
  /** How far the room in the foil is shifted. */
  room: Vec2;
}

/** A card as it is drawn. */
export interface CardModel {
  info: CardInfo;
  /** Drawn from its smaller picture (Kit.small), front up. */
  small?: boolean;
  p: Pose;
  /** A springy bow along its height. */
  bend: number;
  /** A band of light crossing it, -0.5 to 1.5, and how strong. */
  sheen: number; sheenAmt: number;
  flash: number;
  /** Where the mouth of the bag it comes out of is, how far it is still in its shade, and the light it stands in. */
  lip: number; lipOn: number; lipLight: number;
  /** The same band, crossing its small picture. */
  gleam: number;
  /** Leaning toward the pointer, -1 to 1 either way, by as much as `amp` degrees. */
  tiltX: number; tiltY: number; amp: number;
  /** How much it floats. */
  float: number;
  /** How far the signature is written: 0 to 1, less for none yet, more once it is done. */
  signT: number;
  /** A band of light along the ink, -0.5 to 1.9. */
  gleamInk: number;
  /** The pen's tip while it writes: where, in texels, and how bright. */
  tip: Vec2; tipAmt: number;
}
export const cardModel = (info: CardInfo): CardModel => ({
  info, p: P(), bend: 0, sheen: -1, sheenAmt: 0, flash: 0, lip: 0, lipOn: 0, lipLight: 0, gleam: -2,
  tiltX: 0, tiltY: 0, amp: 18, float: 0, signT: info.signed ? -1 : 2, gleamInk: -1, tip: [0, 0], tipAmt: 0,
});
/** A card turned by hand, in degrees. */
export interface Turn { yaw: number; pitch: number }

/** A bag as it is drawn. */
export interface BagModel {
  /** What is in it tells the light it holds. */
  card: { info: CardInfo };
  p: Pose;
  /** Makes it a little unlike the others, and mirrors its film. */
  seed: number; flip: number;
  /** The seal: how far it is through, what is drawn of that, and whether it is open. */
  q: number; shown: number; torn: boolean;
  /** Where along the flap the hand holds it, 0 to 1; the roll of the part pulled up: how far round, and its radius. */
  gx: number; curl: number; rad: number;
  /** The mouth, the air in it, whether the card is inside. */
  open: number; air: number; full: number;
  /** The film bowing as it is moved. */
  bx: number; by: number;
  /** The top drawn toward us, the loose flap rippling, bent about once it is let go of. */
  lift2: number; wave: number; crush: number;
  /** The flap about to give a little more. */
  strain: number;
  /** A glint running along the flap's edge; below -1 for none. */
  hint: number;
  lit: number;
  /** The light inside as far as it has got out, and the beam out of the open mouth, 0 to 1. */
  glow: number; beam: number;
}
export const bagModel = (card: { info: CardInfo }, seed: number, flip: number): BagModel => ({
  card, p: P(), seed, flip, q: 0, shown: 0, torn: false, gx: 0.5, curl: 0.6, rad: 0.42, open: 0, air: 0.3, full: 1,
  bx: 0, by: 0, lift2: 0, wave: 2.4, crush: 0, strain: 0, hint: -2, lit: 1, glow: 0, beam: 0,
});

/** The box as it is drawn; its angles in degrees, for a lid that is shut. */
export interface BoxModel { series: string; p: Pose; lid: number; tuck: number; flaps: number; lit: number }
export const boxModel = (series: string, p: Pose): BoxModel => ({ series, p, lid: 90, tuck: -90, flaps: 90, lit: 1 });

/** A particle: 0 a sliver of foil, 1 a spark, 2 a mote of dust. It is drawn from `life` 0 to `max`. */
export interface Bit {
  x: number; y: number;
  size: number; spin: number;
  kind: 0 | 1 | 2;
  c: Vec3;
  life: number; max: number;
}

/** Light nobody has coloured yet. */
export const PALE: readonly Vec3[] = [[0.86, 0.84, 0.94]];
/** How strong a bag's light is, how far up it reaches, and how far down it sits: the nearer the mouth, the wider it
 * fans. `warm` and `dusk`: how far the desk takes its colours and goes dark. */
export interface Glow { power: number; reach: number; deep: number; warm: number; dusk: number }
const GLOW: Record<CardInfo["kind"] | "signed", Glow> = {
  solo: { power: 0.50, reach: 84, deep: 420, warm: 0.12, dusk: 0.14 },
  duo: { power: 0.86, reach: 150, deep: 215, warm: 0.26, dusk: 0.58 },
  group: { power: 1.0, reach: 176, deep: 150, warm: 0.34, dusk: 0.64 },
  signed: { power: 1.16, reach: 186, deep: 205, warm: 0.36, dusk: 0.64 },
};
export const glowOf = (info: CardInfo): Glow => GLOW[info.signed ? "signed" : info.kind];

/** "over": what is drawn covers what lies under it. "light": light of its own over that. "add": light alone. */
export type Blend = "over" | "light" | "add";
export interface BagOptions { p?: Pose; lit?: number; between?: (() => void) | null }
export interface FoilOptions { lit?: number; low?: boolean; cut?: 0 | 1 | 2 }
/** 0 the body, 1 the flap, 2 the body's near side once open, 3 its far side, seen from inside. */
export type FoilPiece = 0 | 1 | 2 | 3;

export interface Painter {
  /** What follows belongs to this picture. */
  begin(frame: Frame): void;
  blend(kind: Blend): void;
  /** The blending set last. */
  readonly blended: Blend;
  /** For bags, boxes and cards: the depth test, and blending "over". */
  solid(): void;
  clearDepth(): void;
  /** Covers the view, [w] by [h] design units. `lift`: lighter all over. `cover`: how far it has closed in on `at`.
   *  `series`: it is the floor of that series' stage, where there is one. */
  desk(
    w: number, h: number, dark: number, tone: number, lights: readonly Vec3[], lift?: number, cover?: number, at?: Vec2, series?: string,
  ): void;
  /** A soft patch of shade on the ground. */
  disc(x: number, y: number, w: number, h: number, color: Vec3, alpha: number, soft: number): void;
  shadow(x: number, y: number, w: number, h: number, rz: number, alpha: number, grow?: number, tone?: Vec3): void;
  foil(b: BagModel, p: Pose, piece: FoilPiece, o?: FoilOptions): void;
  /** A bag in hand or falling, with its light; `between` draws a card that stands in its mouth. */
  bag(b: BagModel, o?: BagOptions): void;
  /** The light under the flap, and out of the mouth. */
  slit(b: BagModel, p: Pose, k?: number): void;
  beam(b: BagModel, p: Pose, k?: number): void;
  /** A card at full size; nothing while its textures are not there. */
  card(c: CardModel, p: Pose, turn?: Turn | null): void;
  /** Its small picture, on a slip of board; nothing while it is not there. */
  thumb(c: CardModel, lit: number): void;
  /** What stands in the box is drawn after its back and before its front. */
  box(b: BoxModel, lit: number, part?: "back" | "front"): void;
  /** Slivers of foil, or what glows. */
  bits(list: readonly Bit[], glowing: boolean): void;
  rays(x: number, y: number, amount: number, lights: readonly Vec3[]): void;
  /** Covers the view with light. */
  wash(w: number, h: number, tone: Vec3, amount: number): void;
}

const lightU = (l: readonly Vec3[]): Uniforms => (
  { u_n: l.length, u_c1: l[0], u_c2: l[1] ?? l[0], u_c3: l[2] ?? l[1] ?? l[0] });
const T = (x: number, y: number, z: number): Mat4 => G.move(x, y, z);
const M = (...a: Mat4[]): Mat4 => a.reduce((m, n) => G.mul(m, n));
const dimOf = (info: CardInfo): Vec2 => (info.land ? [CARD_H, CARD_W] : [CARD_W, CARD_H]);

export function createPainter(gl: GL, kit: Kit): Painter {
  const { progs, mesh, tex } = kit;
  let { vp, px, clock, lamp, room }: Frame = { vp: G.ident(), px: 1, clock: 0, lamp: [0, 0, 230], room: [0, 0] };

  let blended: Blend = "over";
  function blend(kind: Blend): void {
    blended = kind;
    // The canvas keeps its own opacity: covered where something covers it, as it was where light falls.
    if (kind === "over") gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    else gl.blendFunc(gl.ONE, kind === "light" ? gl.ONE_MINUS_SRC_ALPHA : gl.ONE);
  }
  const clearDepth = () => gl.clear(gl.DEPTH_BUFFER_BIT);
  const solid = () => { gl.enable(gl.DEPTH_TEST); blend("over"); };

  function flat(
    prog: Program, model: Mat4, dim: Vec2, values: Uniforms = {}, texture: WebGLTexture | null = null,
    rect: Vec4 = [0, 0, 1, 1],
  ): void {
    prog.use();
    if (texture) prog.tex("u_tex", 0, texture);
    prog.set({ u_vp: vp, u_model: model, u_dim: dim, u_rect: rect, ...values });
    mesh.quad.draw();
  }
  function shadow(
    x: number, y: number, w: number, h: number, rz: number, alpha: number, grow = 1.6, tone: Vec3 = BLACK,
  ): void {
    gl.disable(gl.DEPTH_TEST);
    blend("over");
    flat(progs.shadow, G.pose(P(x, y, { rz })), [w * grow, h * grow], { u_alpha: alpha, u_tone: tone }, tex.shadow);
  }

  /* ---------------------------------------------------------------- bags */
  /** The first of the light is pale, whoever is in there; its colours part as the flap goes up. */
  function lightNow(b: BagModel): readonly Vec3[] {
    const k = smooth(0.10, 0.46, b.glow);
    const { light } = b.card.info;
    if (k >= 1) return light;
    const [pale] = PALE;
    return light.map((t): Vec3 => [lerp(pale[0], t[0], k), lerp(pale[1], t[1], k), lerp(pale[2], t[2], k)]);
  }
  const breath = (b: BagModel) => 1 + 0.05 * Math.sin(clock / 640 + b.seed);

  function foil(b: BagModel, p: Pose, piece: FoilPiece, o: FoilOptions = {}): void {
    const f = progs.foil;
    f.use();
    f.tex("u_room", 1, tex.room);
    f.set({
      u_vp: vp, u_model: G.pose(p), u_size: BAG, u_flap: FLAP, u_piece: piece, u_q: b.shown, u_grip: b.gx,
      u_rad: b.rad * FLAP, u_curl: b.curl, u_open: b.open, u_air: b.air, u_bend: [b.bx, b.by], u_lift: b.lift2,
      u_wave: b.wave, u_crush: b.crush,
      u_glow: b.glow > 0.003 ? b.glow * glowOf(b.card.info).power : 0, ...lightU(b.glow > 0.003 ? lightNow(b) : PALE),
      u_cut: o.cut ?? 0, u_closed: piece === 0 && b.q <= 0 && b.shown < 0.002 ? 1 : 0, u_full: b.full, u_seed: b.seed,
      u_flip: b.flip, u_room_shift: room, u_lamp: lamp, u_lit: o.lit ?? b.lit, u_hint: b.hint,
      u_strain: b.q > 0 ? b.strain : 0,
    });
    (piece === 1 ? mesh.flap : o.low ? mesh.low : mesh.fine).draw();
  }
  /** Over the bag: light adds to what lies under it, and colours it. */
  function glowing(prog: Program, model: Mat4, dim: Vec2, values: Uniforms): void {
    gl.disable(gl.DEPTH_TEST);
    blend("light");
    flat(prog, model, dim, { u_time: clock / 1000, ...values });
    solid();
  }
  function slit(b: BagModel, p: Pose, k = 1): void {
    const amt = b.glow * glowOf(b.card.info).power * breath(b) * k;
    if (amt < 0.004) return;
    const w = BAG[0] * 2.0, h = 340, top = 110;
    glowing(progs.slit, M(G.pose(p), T(0, -BAG[1] / 2 - top + h / 2, 6)), [w, h], {
      u_bag: [BAG[0], top], u_flap: FLAP, u_q: b.shown, u_grip: b.gx, u_rad: b.rad * FLAP, u_amt: amt,
      ...lightU(lightNow(b)),
    });
  }
  function beam(b: BagModel, p: Pose, k = 1): void {
    const g = glowOf(b.card.info), amt = b.beam * g.power * breath(b) * k;
    if (amt < 0.004) return;
    const w = 940, h = 600, foot = 70;
    glowing(progs.beam, M(G.pose(p), T(0, -BAG[1] / 2 + foot - h / 2, 2)), [w, h], {
      u_mouth: 1 - foot / h, u_half: BAG[0] * 0.455, u_deep: g.deep, u_reach: g.reach * (0.45 + 0.55 * b.beam),
      u_amt: amt, ...lightU(b.card.info.light),
    });
  }
  function bag(b: BagModel, { p = b.p, lit, between }: BagOptions = {}): void {
    if (!b.torn) {
      foil(b, p, 0, { lit });
      if (b.q > 0) { foil(b, p, 1, { lit }); slit(b, p); }
      return;
    }
    // Open: what stands up of the flap is behind everything, then the dark inside, the card, the near side, and over it
    // whatever of the flap has not gone up yet.
    foil(b, p, 1, { lit, cut: 1 });
    clearDepth();
    foil(b, p, 3, { lit });
    // Most of the light stands behind the card, a little of it before.
    beam(b, p, 0.92);
    if (between) { gl.disable(gl.DEPTH_TEST); between(); gl.enable(gl.DEPTH_TEST); }
    clearDepth();
    foil(b, p, 2, { lit });
    clearDepth();
    foil(b, p, 1, { lit, cut: 2 });
    beam(b, p, 0.26);
    slit(b, p, 1 - b.beam);
  }

  /* ---------------------------------------------------------------- cards */
  function card(c: CardModel, p: Pose, turn: Turn | null = null): void {
    const sides = kit.faces(c.info, c.small);
    if (!sides) return;
    const dim = dimOf(c.info);
    // Leaning and turning by hand go about the screen's axes, over the card's own pose.
    const leanY = c.tiltX * c.amp + (turn ? turn.yaw : 0), leanX = -c.tiltY * c.amp * 0.85 + (turn ? turn.pitch : 0);
    const yaw = p.ry + leanY, pitch = p.rx + leanX;
    const y = p.y + 2.2 * Math.sin(clock / 1200) * c.float;
    const m = M(
      T(p.x, y, p.z), G.rotX(leanX * RAD), G.rotY(leanY * RAD), G.rotZ(p.rz * RAD), G.rotY(p.ry * RAD),
      G.rotX(p.rx * RAD), G.scale(p.s, p.s, p.s),
    );
    // The light stays where it is while the card turns under it.
    const half = (a: number) => ((a + 90) % 180 + 180) % 180 - 90;
    const light: Vec2 = [
      clamp(0.5 + 1.35 * Math.sin(half(yaw) * RAD), -0.25, 1.25),
      clamp(0.46 - 1.35 * Math.sin(half(pitch) * RAD), -0.25, 1.25),
    ];
    // Which of its sides face the eye: the one that lies [r] along the column [col], on one end or the other ([d]).
    const sees = (col: number, r: number, d: number) => {
      const k = 1 / p.s, nx = m[col] * k * d, ny = m[col + 1] * k * d, nz = m[col + 2] * k * d;
      return nx * -(m[12] + nx * r) + ny * -(m[13] + ny * r) + nz * (G.DIST - (m[14] + nz * r)) > 0;
    };
    const rims = [
      sees(0, dim[0] * p.s / 2, -1), sees(0, dim[0] * p.s / 2, 1),
      sees(4, dim[1] * p.s / 2, -1), sees(4, dim[1] * p.s / 2, 1),
    ];
    const r = progs.rim;
    r.use();
    r.tex("u_noise", 2, tex.noise);
    rims.forEach((on, k) => {
      if (!on) return;
      r.set({
        u_vp: vp, u_model: m, u_dim: dim, u_bend: c.bend, u_thick: THICK, u_face: 0, u_rim: k + 1, u_lit: 1,
        u_lip: c.lip, u_lipOn: c.lipOn,
      });
      mesh.strip.draw();
    });
    const face = sees(8, THICK * p.s / 2, 1) ? 1 : sees(8, THICK * p.s / 2, -1) ? -1 : 0;
    if (!face) return;
    const { info } = c, sign = info.signed, ink = kit.sign(info);
    const g = progs.card;
    g.use();
    g.tex("u_base", 0, sides.base);
    g.tex("u_mat", 1, sides.mat);
    g.tex("u_noise", 2, tex.noise);
    g.tex("u_baseB", 3, sides.baseB);
    g.tex("u_matB", 4, sides.matB);
    g.tex("u_sign", 5, ink ?? tex.noise);
    g.set({
      u_vp: vp, u_model: m, u_dim: dim, u_size: info.size, u_light: light,
      u_scale: info.size[0] / Math.max(1, dim[0] * p.s * px), u_on: 1,
      u_foilDark: info.foil.dark, u_foilLit: info.foil.lit, u_printDark: info.print.dark, u_printLit: info.print.lit,
      u_silverDark: SILVER.dark, u_silverLit: SILVER.lit,
      u_bend: c.bend, u_thick: THICK, u_face: face, u_rim: 0, u_lit: 1, u_lip: c.lip, u_lipOn: c.lipOn,
      u_sheen: c.sheen, u_sheenAmt: c.sheenAmt, u_tone: info.tones[0], u_flash: c.flash,
      u_signBox: sign && ink ? sign.box : NONE, u_signT: c.signT, u_signGleam: c.gleamInk,
      u_tip: [c.tip[0], c.tip[1], c.tipAmt],
      u_lipLight: c.lipLight, ...lightU(info.light),
    });
    mesh.card.draw();
  }
  function thumb(c: CardModel, lit: number): void {
    const sheet = kit.thumbs(c.info.series);
    if (!sheet.drawn) return;
    const rect = sheet.rect(c.info.id), dim = dimOf(c.info);
    const t = THICK * c.p.s, sign = c.info.signed, ink = kit.sign(c.info);
    gl.disable(gl.DEPTH_TEST);
    progs.thumb.use();
    progs.thumb.tex("u_sign", 1, ink ?? tex.noise);
    flat(progs.thumb, G.pose({ ...c.p, x: c.p.x + t * 0.35, y: c.p.y + t }), dim,
      { u_lit: lit, u_gleam: -9, u_solid: 1, u_signBox: NONE }, sheet.texture, rect);
    flat(progs.thumb, G.pose(c.p), dim,
      { u_lit: lit, u_gleam: c.gleam, u_solid: 0, u_signBox: sign && ink ? sign.uv : NONE }, sheet.texture, rect);
  }

  /* ---------------------------------------------------------------- the box */
  interface Panel { lit: number; print?: Vec4; dark?: number; edge?: number; fold?: Vec4; corner?: Vec2 }
  function panel(m: Mat4, dim: Vec2, o: Panel): void {
    progs.box.set({
      u_vp: vp, u_model: m, u_dim: dim, u_print: o.print ?? [0, 0, 1, 1], u_inked: o.print ? 1 : 0, u_lit: o.lit,
      u_lamp: lamp, u_dark: o.dark ?? 0, u_edge: o.edge ?? 0, u_fold: o.fold ?? NONE, u_radius: o.fold ? FOLD : 0,
      u_bow: o.fold ? 0.045 : 0, u_corner: o.corner ?? [0, 0],
    });
    (o.fold ? mesh.board : mesh.quad).draw();
  }
  /** A piece of board with its cut edges; `edges` names the sides that show: t, b, l, r. */
  function slab(m: Mat4, w: number, h: number, edges: string, o: Panel): void {
    const t = BOARD, q = Math.PI / 2;
    panel(m, [w, h], o);
    panel(M(m, T(0, 0, -t)), [w, h], { lit: o.lit, corner: o.corner });
    const e: Panel = { lit: o.lit, edge: 1 };
    // Cut edges stop short of rounded corners and of the folds.
    const [ct, cb] = o.corner ?? [0, 0], cut = FOLD * 0.3;
    const y0 = -h / 2 + (o.fold?.[2] ? cut : ct), y1 = h / 2 - (o.fold?.[3] ? cut : cb);
    if (edges.includes("t")) panel(M(m, T(0, -h / 2, -t / 2), G.rotX(q)), [w - 2 * ct, t], e);
    if (edges.includes("b")) panel(M(m, T(0, h / 2, -t / 2), G.rotX(-q)), [w - 2 * cb, t], e);
    if (edges.includes("l")) panel(M(m, T(-w / 2, (y0 + y1) / 2, -t / 2), G.rotY(-q)), [t, y1 - y0], e);
    if (edges.includes("r")) panel(M(m, T(w / 2, (y0 + y1) / 2, -t / 2), G.rotY(q)), [t, y1 - y0], e);
  }
  function box(b: BoxModel, lit: number, part?: "back" | "front"): void {
    const [w, h, d] = BOX, t = BOARD, q = Math.PI / 2, gap = 1.2;
    const m = G.pose(b.p);
    const g = progs.box, look = seriesArt(b.series)?.look;
    const print = kit.print(b.series);
    if (!print || !look) return;
    g.use();
    g.tex("u_ink", 0, print);
    g.tex("u_noise", 1, tex.noise);
    g.set({ u_board: look.box, u_rub: look.rub });
    const edge: Panel = { lit, edge: 1 };
    if (part !== "front") {
      const side: Vec4 = [780 / 1280, 0, 1180 / 1280, 1];
      // Walls: the printed face, then the board's inside, set in by its thickness. Nothing shares a plane.
      const back = M(m, T(0, 0, -d / 2), G.rotY(Math.PI));
      const all: Vec4 = [1, 1, 1, 1];
      panel(back, [w, h], { lit, dark: 1, fold: all, print: [0, 0, 755 / 1280, 1] });
      panel(M(back, T(0, (t + gap) / 2, -t)), [w - 2 * t, h - t - gap], { lit, dark: 1 });
      const floor = M(m, T(0, h / 2, 0), G.rotX(-q));
      panel(floor, [w, d], { lit, dark: 1, fold: all });
      panel(M(floor, T(0, 0, -t)), [w - 2 * t, d - 2 * t], { lit, dark: 1 });
      for (const s of [-1, 1]) {
        const wall = M(m, T(s * w / 2, 0, 0), G.rotY(s * q));
        panel(wall, [d, h], { lit, dark: 1, fold: all, print: side });
        panel(M(wall, T(0, (t + gap) / 2, -t)), [d - 2 * t, h - t - gap], { lit, dark: 1 });
        panel(M(m, T(s * (w / 2 - t / 2), -h / 2 + gap, 0), G.rotX(q)), [t, d - 2 * t], edge);
      }
      panel(M(m, T(0, -h / 2 + gap, -d / 2 + t / 2), G.rotX(q)), [w - 2 * gap, t], edge);
      // The dust flaps tuck under the lid, so their hinge drops by its thickness as they close.
      const shut = clamp(b.flaps / 90), fl = 13 * MM, fw = d - 4 * t - 8;
      for (const s of [-1, 1]) {
        const hinge = T(s * (w / 2 - gap * shut), -h / 2 + (t + gap) * shut, 0);
        const f = M(m, hinge, G.rotY(s * q), G.rotX(b.flaps * RAD), T(0, -fl / 2, 0));
        slab(f, fw, fl, "tlr", { lit, fold: [0, 0, 0, 1], corner: [5 * MM, 0] });
      }
      // The lid reaches the inside of the front wall, and its tongue goes down behind that.
      const lw = w - 2 * FOLD * 0.3, ld = d - t - gap, tw = w - 2 * t - 8, th = 11 * MM;
      const lid = M(m, T(0, -h / 2, -d / 2), G.rotX(b.lid * RAD), T(0, ld / 2, 0));
      slab(lid, lw, ld, "lr", { lit, fold: [0, 0, 1, 1] });
      panel(M(lid, T(0, ld / 2, -t / 2), G.rotX(-q)), [lw, t], edge);
      const tongue = M(lid, T(0, ld / 2, 0), G.rotX(b.tuck * RAD), T(0, th / 2, 0));
      slab(tongue, tw, th, "blr", { lit, fold: [0, 0, 1, 0], corner: [0, 6 * MM] });
    }
    if (part !== "back") {
      const front = M(m, T(0, 0, d / 2));
      panel(M(front, T(0, 0, -t)), [w - 2 * gap, h], { lit });
      panel(front, [w, h], { lit, fold: [1, 1, 0, 1], print: [0, 0, 755 / 1280, 1] });
      panel(M(m, T(0, -h / 2, d / 2 - t / 2), G.rotX(q)), [w - FOLD * 0.6, t], edge);
    }
  }

  /* ---------------------------------------------------------------- desk, light, particles */
  function bits(all: readonly Bit[], glow: boolean): void {
    const list = all.filter((f) => f.life >= 0 && (glow ? f.kind > 0 : !f.kind));
    if (!list.length) return;
    const data = new Float32Array(list.length * 8);
    list.forEach((f, i) => {
      const k = f.life / f.max, fade = f.kind ? Math.min(1, f.life / 220) * (1 - k) ** 1.5 : 1;
      const size = f.size * (f.kind ? 1 : 1 - 0.5 * k);
      data.set([f.x, f.y, size, f.kind, f.c[0] * fade, f.c[1] * fade, f.c[2] * fade, f.spin], i * 8);
    });
    progs.bits.use();
    progs.bits.set({ u_vp: vp });
    gl.disable(gl.DEPTH_TEST);
    blend(glow ? "add" : "over");
    kit.bits.draw(data, list.length);
  }

  return {
    begin(frame) { ({ vp, px, clock, lamp, room } = frame); },
    blend,
    get blended() { return blended; },
    solid, clearDepth, shadow, foil, bag, slit, beam, card, thumb, box, bits,
    desk(w, h, dark, tone, lights, lift = 0, cover = 1, at = [0, 0], series) {
      gl.disable(gl.DEPTH_TEST);
      blend("over");
      const far = series ? kit.floor(series) : null, ground = far && seriesArt(series!)!.stage!.look.ground;
      progs.desk.use();
      progs.desk.tex("u_noise", 1, tex.noise);
      progs.desk.tex("u_far", 2, far ?? tex.noise);
      flat(progs.desk, G.ident(), [w + 60, h + 60], {
        u_view: [w, h], u_spot: dark, u_toneAmt: tone, u_lampAt: [lamp[0], lamp[1]], u_lift: lift, u_cover: cover,
        u_coverAt: at, u_floor: far ? 1 : 0, u_top: ground?.[0] ?? [0, 0, 0], u_bottom: ground?.[1] ?? [0, 0, 0], ...lightU(lights),
      });
    },
    disc(x, y, w, h, color, alpha, soft) {
      gl.disable(gl.DEPTH_TEST);
      blend("over");
      flat(progs.disc, G.pose(P(x, y)), [w, h], { u_color: [...color, alpha], u_soft: soft });
    },
    rays(x, y, amount, lights) {
      gl.disable(gl.DEPTH_TEST);
      blend("add");
      flat(progs.rays, G.pose(P(x, y)), [1500, 1500], { u_time: clock / 1000, u_amt: amount, ...lightU(lights) });
    },
    wash(w, h, tone, amount) {
      if (amount < 0.005) return;
      gl.disable(gl.DEPTH_TEST);
      blend("light");
      flat(progs.wash, G.ident(), [w + 60, h + 60], { u_color: [...tone, amount], u_round: 0.75 });
    },
  };
}

/** The shade of a box that stands on paper. */
export function groundShade(painter: Painter, { p }: BoxModel, k = 1): void {
  const foot = p.y + BOX[1] * p.s / 2, wide = BOX[0] * p.s;
  painter.disc(p.x + 6, foot + 4, wide * 1.9, 159 * p.s, PLUM, 0.26 * k, 2.2);
  painter.disc(p.x + 4, foot + 1, wide * 1.34, 72 * p.s, PLUM, 0.42 * k, 1.6);
}
