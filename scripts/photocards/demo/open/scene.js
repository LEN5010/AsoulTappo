// Opening a box: the purple box lands and opens, twenty silver bags come out, each is torn along its top and gives up
// one card, face down; a card turns over on its own, a sideways one (two members, or the group) stops the table and
// turns over in the dark. A signed one is held up while its signature is written.
// The light in a bag tells what is in it as it is torn: one colour for each member on the card, gold for a signed one.
// Everything is drawn in one canvas.
import * as ART from "../catalog.js";
import * as G from "./gl.js";
import * as SH from "./shaders.js";
import * as snd from "./sound.js";

const params = new URLSearchParams(location.search);
const MANUAL = params.has("manual");
const CALM = matchMedia("(prefers-reduced-motion: reduce)").matches && !params.has("motion");
const STAGE_W = 960, STAGE_H = 640;
const COUNT = 20;
// Millimetres of the real things, and the size they have in the middle of the stage.
const MM = 400 / 97;
const BAG = [62 * MM, 90 * MM], FLAP = 18 * MM;   // the body, and the flap folded over it
const CARD_W = 54 * MM, CARD_H = 86 * MM;
const BOX = [73.5 * MM, 100 * MM, 38 * MM], BOARD = 1.4 * MM;
const THICK = 1.0 * MM;      // a card's thickness
const TEETH = 30;
const RAD = Math.PI / 180;

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
let seed = Number(params.get("seed") ?? (MANUAL ? 7 : Math.floor(Math.random() * 1e9)));
function rand() { seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
const rnd = (a, b) => a + (b - a) * rand();
const pick = (list) => list[Math.floor(rand() * list.length)];
function shuffle(list) { for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [list[i], list[j]] = [list[j], list[i]]; } return list; }

/* ---------------------------------------------------------------- time */
// Moves start softly and settle: `out` like a damped spring, `flow` like a hand's unhurried reach.
const damped = (n) => (t) => 1 - (1 - t) ** n * (1 + n * t);
// `glide`: eased out of the box, quickest on the way, a long settling at the end.
const E = { glide: (t) => 1 - (1 - t ** 1.7) ** 3.2, linear: (t) => t, out: damped(4), quick: damped(6), flow: (t) => t * t * t * (t * (6 * t - 15) + 10) };
let clock = 0;
let tweens = [];
let timers = [];
/** Runs a fresh number each box, so what an older box still had queued falls silent. */
let epoch = 0;

const pace0 = new WeakMap();   // how fast each thing was going, so the next move takes over without a jolt
function tween(o, to, ms, ease = E.out, delay = 0) {
  for (const t of tweens) if (t.o === o && !t.from) for (const k in to) delete t.to[k];
  return new Promise((done) => { tweens.push({ o, to: { ...to }, from: null, v: {}, ms: Math.max(1, ms), ease, at: -delay, done }); });
}
const wait = (ms) => new Promise((done) => timers.push({ left: ms, done }));
function advance(dt) {
  clock += dt;
  for (const t of [...timers]) {
    t.left -= dt;
    if (t.left <= 0) { timers.splice(timers.indexOf(t), 1); t.done(); }
  }
  for (const t of [...tweens]) {
    t.at += dt;
    if (t.at < 0) continue;
    let v = pace0.get(t.o);
    if (!v) pace0.set(t.o, v = {});
    if (!t.from) {
      for (const u of tweens) if (u !== t && u.o === t.o && u.from) for (const k in t.to) delete u.to[k];
      t.from = {};
      for (const k in t.to) { t.from[k] = t.o[k] ?? 0; t.v[k] = v[k] ?? 0; }
    }
    const k = clamp(t.at / t.ms), e = t.ease(k), carry = t.ms * k * (1 - k) ** 3;
    for (const p in t.to) {
      const x = t.from[p] + (t.to[p] - t.from[p]) * e + t.v[p] * carry;
      v[p] = k >= 1 ? 0 : (x - (t.o[p] ?? 0)) / Math.max(1, dt);
      t.o[p] = x;
    }
    if (k >= 1) { tweens.splice(tweens.indexOf(t), 1); t.done(); }
  }
}
const P = (x = 0, y = 0, o = {}) => ({ x, y, z: 0, rx: 0, ry: 0, rz: 0, s: 1, ...o });
const copy = (p) => ({ ...p });

/* ---------------------------------------------------------------- set-up */
const canvas = document.getElementById("gl");
const gl = G.context(canvas);
const hud = document.getElementById("hud"), countEl = document.getElementById("count");
const autoKey = document.getElementById("auto"), againKey = document.getElementById("again"), soundKey = document.getElementById("sound");
let view = { w: STAGE_W, h: STAGE_H, px: 1, css: 1 };
function fit() {
  const dpr = params.has("dpr") ? Number(params.get("dpr")) : Math.min(2, window.devicePixelRatio || 1);
  const cw = canvas.clientWidth || 960, ch = canvas.clientHeight || 640;
  const css = Math.min(cw / STAGE_W, ch / STAGE_H);
  canvas.width = Math.round(cw * dpr);
  canvas.height = Math.round(ch * dpr);
  view = { w: cw / css, h: ch / css, px: css * dpr, css };
}
addEventListener("resize", fit);

const page = await (await fetch("index.html", { cache: "no-store" })).text();
const progs = {
  foil: G.program(gl, SH.FOIL_VS, SH.FOIL_FS),
  card: G.program(gl, SH.CARD_VS, SH.cardFs(page)),
  rim: G.program(gl, SH.CARD_VS, SH.RIM_FS),
  box: G.program(gl, SH.BOX_VS, SH.BOX_FS),
  shadow: G.program(gl, SH.FLAT_VS, SH.SHADOW_FS),
  thumb: G.program(gl, SH.FLAT_VS, SH.THUMB_FS),
  desk: G.program(gl, SH.FLAT_VS, SH.DESK_FS),
  rays: G.program(gl, SH.FLAT_VS, SH.RAYS_FS),
  slit: G.program(gl, SH.FLAT_VS, SH.SLIT_FS),
  beam: G.program(gl, SH.FLAT_VS, SH.BEAM_FS),
  wash: G.program(gl, SH.FLAT_VS, SH.WASH_FS),
  bits: G.program(gl, SH.BIT_VS, SH.BIT_FS),
};
const mesh = { quad: G.grid(gl, 1, 1), fine: G.grid(gl, 36, 52), low: G.grid(gl, 14, 18), strip: G.grid(gl, 72, 5), card: G.grid(gl, 44, 56), board: G.grid(gl, 20, 20), flap: G.grid(gl, 16, 32) };
const tex = {};
[tex.room, tex.shadow, tex.ink] = (await Promise.all([`${ART.OPEN}room.webp`, `${ART.OPEN}shadow.webp`, ART.BOX].map(G.image))).map((i) => G.texture(gl, i));
{
  // The same random texels as the card page's grain.
  const noise = new Uint8Array(256 * 256 * 4);
  let s = 20261123;
  for (let i = 0; i < noise.length; i++) { s = (s * 1664525 + 1013904223) >>> 0; noise[i] = s >>> 24; }
  tex.noise = G.texture(gl, null, { mips: false, repeat: true });
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 256, 0, gl.RGBA, gl.UNSIGNED_BYTE, noise);
}
/* ---------------------------------------------------------------- cards */
// Signatures, by member: where one lies on the card, and how long it takes to write.
const { cards: CARDS, signs: SIGNS } = await ART.catalog();
const TONES = { diana: [0.98, 0.66, 0.77], bella: [0.98, 0.58, 0.52], eileen: [0.55, 0.68, 0.98] };
for (const c of CARDS) {
  c.land = c.size[0] > c.size[1];
  // The colours lie the way the members stand.
  c.tones = c.stand.map((k) => TONES[k]);
}
gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
await Promise.all(Object.entries(SIGNS).map(async ([k, s]) => {
  s.tex = G.texture(gl, await G.image(ART.sign(k)));
  s.uv = [s.box[0] / 1080, s.box[1] / 1720, s.box[2] / 1080, s.box[3] / 1720];
}));
gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.BROWSER_DEFAULT_WEBGL);
const bySolo = CARDS.filter((c) => c.kind === "solo"), byDuo = CARDS.filter((c) => c.kind === "duo"), byGroup = CARDS.filter((c) => c.kind === "group");
// Small pictures of every card, for the row at the bottom and the final spread.
const ATLAS = 2048;
const atlas = document.createElement("canvas");
atlas.width = atlas.height = ATLAS;
const pen = atlas.getContext("2d");
tex.atlas = G.texture(gl, atlas);
{
  let p = 0, l = 0;
  for (const c of CARDS) {
    const w = c.land ? 500 : 250, h = c.land ? 314 : 398;
    const n = c.land ? l++ : p++;
    const x = c.land ? (n % 4) * 512 + 4 : (n % 8) * 256 + 3, y = c.land ? 840 + Math.floor(n / 4) * 326 : Math.floor(n / 8) * 410 + 4;
    c.cell = [x, y, w, h];
    c.rect = [x / ATLAS, y / ATLAS, (x + w) / ATLAS, (y + h) / ATLAS];
  }
}
const GOLD_TONE = [1.0, 0.84, 0.5];
// As light the colours are deeper, or over silver they would all be nearly white. A signed card's is gold alone.
const deep = (t) => t.map((v) => (v / Math.max(...t)) ** 1.8);
for (const c of CARDS) c.light = c.tones.map(deep);
const bySign = bySolo.map((c) => ({ ...c, signed: SIGNS[c.back], tones: [GOLD_TONE, ...c.tones], light: [deep(GOLD_TONE)] }));
/** How strong a bag's light is, how far up it reaches, and how far down it sits: the nearer the mouth, the wider it fans. */
const GLOW = {
  solo: { power: 0.50, reach: 84, deep: 420, warm: 0.12, dusk: 0.14 },
  duo: { power: 0.86, reach: 150, deep: 215, warm: 0.26, dusk: 0.58 },
  group: { power: 1.0, reach: 176, deep: 150, warm: 0.34, dusk: 0.64 },
  signed: { power: 1.16, reach: 186, deep: 205, warm: 0.36, dusk: 0.64 },
};
const glowOf = (info) => GLOW[info.signed ? "signed" : info.kind];
const lightU = (l) => ({ u_n: l.length, u_c1: l[0], u_c2: l[1] ?? l[0], u_c3: l[2] ?? l[1] ?? l[0] });
const PALE = [[0.86, 0.84, 0.94]];
const thumbsReady = (async () => {
  for (const c of CARDS) {
    const img = await G.image(ART.front(c.id)[0]);
    pen.imageSmoothingQuality = "high";
    // In two steps, as one large reduction drops detail.
    const half = document.createElement("canvas");
    half.width = c.cell[2] * 2;
    half.height = c.cell[3] * 2;
    const hp = half.getContext("2d");
    hp.imageSmoothingQuality = "high";
    hp.drawImage(img, 0, 0, half.width, half.height);
    pen.drawImage(half, ...c.cell);
  }
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, tex.atlas);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, atlas);
  gl.generateMipmap(gl.TEXTURE_2D);
})();
const full = new Map();
/** A card's own textures, loaded ahead of its turn and let go a while after. */
function want(name) {
  let f = full.get(name);
  if (!f) {
    f = { used: 0, base: null, mat: null };
    full.set(name, f);
    const [, of, side] = name.match(/^(.*)-(front|back)$/);
    f.ready = Promise.all(ART[side](of).map(G.image)).then(([b, m]) => {
      f.base = G.texture(gl, b);
      f.mat = G.texture(gl, m);
    });
  }
  f.used = clock;
  return f;
}
function letGo(keep) {
  const loose = [...full].filter(([n, f]) => f.base && n.endsWith("-front") && !keep.has(n)).sort((a, b) => a[1].used - b[1].used);
  while (loose.length > 4) {
    const [n, f] = loose.shift();
    gl.deleteTexture(f.base);
    gl.deleteTexture(f.mat);
    full.delete(n);
  }
}
for (const b of ["diana", "bella", "eileen", "landscape"]) want(`${b}-back`);
const SILVER = { dark: [0.36, 0.33, 0.37], lit: [1.0, 0.98, 0.97] };

/* ---------------------------------------------------------------- the box and what is in it */
let box, bags, cards, active, shown, phase, cur, opened, spot, fx, tempo, lastTear, auto, inspecting;
let eager = false;     // a swipe came while a card was still on its way out
let early = false;     // so did a press
let haste = 1;         // how fast a sideways card's ceremony runs; a press during it speeds it up
let wides = 0;         // sideways cards so far in this box
const scene = { spot: 0, dusk: 0, warm: 0, lights: PALE, toneAmt: 0, rays: 0, rayAt: P(), flash: 0, flashTone: [1, 1, 1] };
const RANK = (c) => (c.info.signed ? 3 : c.info.kind === "group" ? 2 : c.info.land ? 1 : 0);

function deal() {
  // A box for looking at: sixteen of one member, one of them signed, three of two, one of the group, anywhere in it.
  const rare = [...shuffle([...byDuo]).slice(0, 3), pick(byGroup)], first = params.get("first");
  const solos = (n) => Array.from({ length: n }, () => pick(bySolo));
  // ?first=sign: the box begins with a signed card of each member.
  if (first === "sign") return [...shuffle(Object.keys(SIGNS)).map((m) => pick(bySign.filter((c) => c.back === m))), ...shuffle([...solos(13), ...rare])];
  // ?first=tiers: one of each kind, the plainest first.
  if (first === "tiers") return [pick(bySolo), rare[0], rare[3], pick(bySign), ...shuffle([...solos(14), ...rare.slice(1, 3)])];
  const order = shuffle([...solos(15), pick(bySign), ...rare]);
  const want0 = CARDS.find((c) => c.id === first) ?? bySign.find((c) => `${c.id}-sign` === first);
  if (want0) order[0] = want0;
  return order;
}

function makeBag(i, card) {
  const thr = new Float32Array(TEETH);
  for (let k = 0; k < TEETH; k++) thr[k] = (k + 0.4 + rnd(-0.28, 0.28)) / TEETH;
  thr[0] = 0.045;                       // the notch has to be started
  thr[TEETH - 1] = 0.985;               // and the last bit holds on
  thr[TEETH - 2] = Math.min(thr[TEETH - 2], 0.94);
  return {
    i, card, row: i, seed: rnd(0, 20), flip: rand() < 0.5 ? 0 : 1, p: P(), state: "box", q: 0, shown: 0, side: 1, n: 0, thr,
    rise: 0, route: null, torn: false, open: 0, air: 0.3, bx: 0, by: 0, vbx: 0, vby: 0, lift2: 0, wave: 2.4, vw: 0, full: 1, gx: 0.5, curl: 0.6, curlV: 0, rad: 0.42, strain: 0, tug: 0, tugV: 0, crush: 0, hint: -2, lit: 1, glow: 0, beam: 0,
  };
}
function makeCard(info) {
  return { info, p: P(), state: "in", bend: 0, sheen: -1, sheenAmt: 0, flash: 0, lip: 0, lipOn: 0, lipLight: 0, thumb: 0, gleam: -2, tiltX: 0, tiltY: 0, amp: 18, float: 0, signT: info.signed ? -1 : 2, gleamInk: -1, tip: [0, 0], tipAmt: 0 };
}

function reset() {
  epoch += 1;
  tweens = [];
  timers = [];
  const ids = deal();
  box = { p: P(0, -760, { rx: -14, ry: 26, s: 0.82 }), lid: 90, tuck: -90, flaps: 90, on: true, lit: 1, sway: 1 };
  bags = ids.map((info, i) => makeBag(i, makeCard(info)));
  cards = bags.map((b) => b.card);
  active = null;
  shown = null;
  phase = "intro";
  cur = -1;
  opened = 0;
  spot = null;
  fx = [];
  tempo = 0;
  lastTear = -1e9;
  inspecting = null;
  eager = early = false;
  haste = 1;
  wides = 0;
  Object.assign(scene, { spot: 0, dusk: 0, warm: 0, lights: PALE, toneAmt: 0, rays: 0, flash: 0 });
  pace0.delete(scene);
  Object.assign(turn, { card: null, yaw: 0, pitch: 0, vy: 0, vp: 0, held: false });
  setAuto(false);
  againKey.classList.add("off");
  autoKey.classList.add("off");
  countEl.classList.remove("on");
  hud.classList.remove("dim");
  void run();
}

/* ---------------------------------------------------------------- pointer */
const ptr = { x: 0, y: 0, vx: 0, vy: 0, down: false, sx: 0, sy: 0, far: 0, dir: 1, moved: 0, used: false, inside: false, speed: 0 };
let pressWaiters = [];
/** The next press, or a swipe that goes on from the last tear. */
const pressed = () => new Promise((done) => pressWaiters.push(done));
function firePress() { const w = pressWaiters; pressWaiters = []; for (const f of w) f(); }
const toStage = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left - r.width / 2) / view.css, (e.clientY - r.top - r.height / 2) / view.css]; };

// A card turned by hand: it keeps going a little when let go of, and comes to rest on one of its faces.
const turn = { card: null, yaw: 0, pitch: 0, vy: 0, vp: 0, to: 0, held: false };
const turnable = () => (phase === "end" ? inspecting : phase === "spot" && shown === spot?.card ? shown : null);
/** What the hand turned becomes the card's own pose again. */
function letTurnGo(c) {
  if (turn.card !== c) return;
  c.p.ry = ((c.p.ry + turn.yaw + 180) % 360 + 360) % 360 - 180;
  c.p.rx += turn.pitch * Math.sign(Math.cos(turn.yaw * RAD) || 1);
  Object.assign(turn, { card: null, yaw: 0, pitch: 0, vy: 0, vp: 0, held: false });
}

let grip = null;       // a tear in hand: where it began
function onMove(x, y, t) {
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
  if (active?.state === "sealed") return tearTo(x, y);
  // After a tear the same stroke may run on. Turning back asks for the next bag and hurries what is on the way.
  if ((y - ptr.far) * ptr.dir > 0) ptr.far = y;
  else if (Math.abs(y - ptr.far) > 44) { ptr.far = y; ptr.dir = -ptr.dir; hurry(0.9); if (shown) firePress(); }
}
function onDown(x, y, t) {
  snd.wake();
  Object.assign(ptr, { x, y, sx: x, sy: y, far: y, t, vx: 0, vy: 0, down: true, moved: 0, used: false, inside: true });
  canvas.classList.add("held");
  grip = null;
  if (phase === "intro") { ptr.used = true; return firePress(); }
  const card = turnable();
  if (card) { if (turn.card !== card) Object.assign(turn, { card, yaw: 0, pitch: 0, vy: 0, vp: 0, to: 0 }); turn.held = true; return; }
  if (phase === "end") { ptr.used = true; return tapEnd(x, y); }
  if (active?.state !== "sealed") { ptr.used = true; ask(); }
}
/** A press while nothing can be taken hold of: go on, or get there sooner. */
function ask() {
  if (spot?.write) spot.write();
  else if (spot && !shown) haste = 4;
  if (phase === "opening" || phase === "gather") haste = 3;
  hurry(0.6);
  if (pressWaiters.length) firePress();
  else if (phase === "play") early = true;
}
function hurry(k) {
  if (phase !== "play" || active?.state === "sealed") return;
  tempo = Math.max(tempo, k);
  eager = true;
}
function onUp() {
  canvas.classList.remove("held");
  const was = ptr.down;
  ptr.down = false;
  if (!was) return;
  if (turn.held) {
    turn.held = false;
    if (ptr.moved < 6) return inspecting ? void putBack() : ask();
    turn.vy = ptr.vx * 0.62;
    turn.vp = -ptr.vy * 0.45;
    turn.to = Math.round((turn.yaw + turn.vy * 240) / 180) * 180;
    return;
  }
  if (active?.state === "sealed") {
    const a = active;
    if (!ptr.used && ptr.moved < 6) void tearAlone(a, 620);
    else if (a.q > 0.72) void tearAlone(a, 260);
  }
  grip = null;
}
canvas.addEventListener("pointerdown", (e) => { canvas.setPointerCapture(e.pointerId); onDown(...toStage(e), e.timeStamp); });
canvas.addEventListener("pointermove", (e) => onMove(...toStage(e), e.timeStamp));
canvas.addEventListener("pointerup", onUp);
canvas.addEventListener("pointercancel", onUp);
canvas.addEventListener("pointerleave", () => { if (!ptr.down) ptr.inside = false; });
addEventListener("keydown", (e) => {
  if (e.key !== " " && e.key !== "Enter") return;
  if (e.target instanceof HTMLButtonElement) return;
  e.preventDefault();
  if (e.repeat && !shown && active?.state !== "sealed") return;
  snd.wake();
  if (phase === "intro") firePress();
  else if (active?.state === "sealed") void tearAlone(active, 560);
  else ask();
});
function setAuto(on) {
  auto = on;
  autoKey.setAttribute("aria-pressed", String(on));
  if (!on) return;
  if (active?.state === "sealed") void tearAlone(active, 420);
  else firePress();
}
autoKey.addEventListener("click", () => { snd.wake(); setAuto(!auto); autoKey.blur(); });
againKey.addEventListener("click", () => { snd.wake(); againKey.blur(); void leave().then(reset); });
soundKey.addEventListener("click", () => { snd.state.on = !snd.state.on; soundKey.textContent = snd.state.on ? "声音 开" : "声音 关"; soundKey.blur(); });

/* ---------------------------------------------------------------- tearing */
/** The flap follows the hand up: each bit of the seal gives once the hand is past it. */
function tearTo(x, y) {
  const a = active;
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
function pull(a, q, speed) {
  if (a.torn) return;
  let broke = 0;
  while (a.n < TEETH && q >= a.thr[a.n]) { breakTooth(a, speed); broke += 1; }
  const low = a.n ? a.thr[a.n - 1] : 0, high = a.n < TEETH ? a.thr[a.n] : 1;
  a.strain = clamp((q - low) / Math.max(0.01, high - low));
  if (broke) a.tugV += broke * 0.010;
  if (a.n >= TEETH) finishTear(a, speed);
}
function breakTooth(a, speed) {
  const k = a.n;
  a.n += 1;
  a.q = a.n / TEETH;
  scene.lights = a.card.info.light;
  snd.tick(a.q, speed, (a.p.x + (a.gx - 0.5) * BAG[0]) / 480, k === 0 ? 1.3 : 1);
}
async function tearAlone(a, ms) {
  if (a.alone || a.torn || a.state !== "sealed") return;
  a.alone = true;
  if (a.n === 0) a.gx = rnd(0.2, 0.8);
  a.hint = -2;
  const hand = { q: a.q };
  const my = epoch;
  a.drive = hand;
  await tween(hand, { q: 1.02 }, ms, (t) => 0.2 * t + 0.8 * E.flow(t));
  if (my === epoch && !a.torn) pull(a, 1.02, 0.7);
}
function finishTear(a, speed) {
  a.torn = true;
  a.q = 1;
  a.strain = 0;
  a.state = "torn";
  const gap = clock - lastTear;
  lastTear = clock;
  tempo = lerp(tempo, 1 - smooth(650, 2000, gap), 0.6);
  eager = early = false;
  ptr.far = ptr.y;
  ptr.dir = -1;
  snd.snap(speed, (a.gx - 0.5) * 0.5);
  // The flap goes on up and over with the hand.
  a.curlV += 0.0008 + 0.0012 * speed;
  a.vw += 0.02;
  void tween(a, { air: 0.55 }, 900, E.flow);
  void tween(a, { beam: 1 }, RANK(a.card) ? 820 : 400, E.flow, RANK(a.card) ? 60 : 0);
  a.tugV -= 0.03;
  a.resolve?.();
}

/* ---------------------------------------------------------------- particles */
function sparks(x, y, n, tones, reach = 0.5, size = 1) {
  for (let i = 0; i < n; i++) {
    const a = rnd(0, Math.PI * 2), v = rnd(0.02, reach);
    const t = pick(tones), k = rnd(0.25, 0.8);
    fx.push({ x: x + Math.cos(a) * 30, y: y + Math.sin(a) * 20, vx: Math.cos(a) * v, vy: Math.sin(a) * v * 0.8, g: 0.00012, size: rnd(7, 22) * size, kind: 1, c: t.map((v2) => lerp(1, v2, 0.55) * k), spin: rnd(0, 0.8), vs: rnd(-0.001, 0.001), life: 0, max: rnd(900, 2200), drag: 0.0022 });
  }
}

/** Dust in the light, rising out of the mouth of [b] over [ms]. */
function motes(b, n, tones, ms) {
  for (let i = 0; i < n; i++) {
    const across = rnd(-0.40, 0.40), t = tones[Math.min(tones.length - 1, Math.floor((across + 0.5) * tones.length))], k = rnd(0.30, 0.85);
    fx.push({ x: b.p.x + across * BAG[0], y: b.p.y - BAG[1] / 2 + rnd(-4, 10), vx: across * rnd(0.04, 0.16), vy: -rnd(0.05, 0.14), g: 0, size: rnd(5, 12), kind: 2, c: t.map((v) => lerp(v, 1, 0.35) * k), spin: 0, vs: 0, life: -rnd(0, ms), max: rnd(1300, 2400), drag: 0.0007 });
  }
}

/* ---------------------------------------------------------------- the sequence */
const railAt = (k) => P((k - (COUNT - 1) / 2) * 33.5, 262, { s: 1, rz: 0 });
const heapAt = (k) => P(350 + (((k * 73) % 100) / 100 - 0.5) * 120, 120 - k * 1.1 + (((k * 41) % 100) / 100 - 0.5) * 56, { rz: ((k * 97) % 360) - 180, s: 0.36 });
const pace = (ms) => ms * lerp(1, 0.46, tempo) * (auto ? 0.62 : 1);

async function run() {
  const my = epoch;
  const live = () => my === epoch;
  if (CALM) { for (let k = 0; k < COUNT; k++) { cards[k].state = "rail"; cards[k].thumb = 1; cards[k].signT = 2; cards[k].p = railAt(k); bags[k].state = "gone"; } box.on = false; opened = COUNT; return finale(); }
  // The box lands.
  await wait(120);
  if (!live()) return;
  void tween(box.p, { y: -6 }, 1250, E.out);
  await wait(620);
  if (!live()) return;
  snd.thud();
  await wait(360);
  if (!live()) return;
  phase = "intro";
  if (!params.has("skipintro")) await pressed();
  if (!live()) return;
  phase = "opening";
  // It turns to face us, the lid goes back.
  box.sway = 0;
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
  phase = "play";
  countEl.classList.add("on");
  autoKey.classList.remove("off");
  await play(live);
  if (live()) await finale();
}
/** Where a bag is while it rises from the box: kept to the box's lean. */
function riseAt(b) {
  const m = G.pose(box.p), y = -b.rise * BOX[1] * 0.98 - 2.5 * MM, z = BOX[2] * (0.42 - (b.i / (COUNT - 1)) * 0.84);
  return [m[4] * y + m[8] * z + m[12], m[5] * y + m[9] * z + m[13], m[6] * y + m[10] * z + m[14]];
}

async function play(live) {
  void want(`${bags[0].card.info.id}-front`);
  for (cur = 0; cur < COUNT; cur++) {
    const b = bags[cur];
    for (let k = cur; k < Math.min(COUNT, cur + 3); k++) void want(`${bags[k].card.info.id}-front`);
    letGo(new Set(bags.slice(Math.max(0, cur - 1), cur + 3).map((x) => `${x.card.info.id}-front`)));
    await arrive(b);
    if (!live()) return;
    await new Promise((done) => { b.resolve = done; if (b.torn) done(); else if (auto) void tearAlone(b, 420); });
    if (!live()) return;
    opened += 1;
    countEl.firstElementChild.textContent = String(opened);
    if (b.card.info.land) await revealWide(b, live);
    else if (b.card.info.signed) await revealSigned(b, live);
    else await revealSolo(b, live);
    if (!live()) return;
  }
}

/** The way from the box to the middle, as one line: straight up out of it, then over in a bow. Evenly measured, so one
 * curve of speed can run along the whole of it. */
function route(b) {
  const from = riseAt(b), clear = riseAt({ i: b.i, rise: 1.04 }), to = [0, 24, 0];
  const up = [0, 1, 2].map((k) => clear[k] - from[k]), straight = Math.hypot(...up);
  const pts = [from, clear];
  const c1 = clear.map((v, k) => v + (up[k] / straight) * 120), c2 = [to[0] - 120, to[1] - 96, 46];
  for (let i = 1; i <= 28; i++) {
    const t = i / 28, s = 1 - t;
    pts.push([0, 1, 2].map((k) => s * s * s * clear[k] + 3 * s * s * t * c1[k] + 3 * s * t * t * c2[k] + t * t * t * to[k]));
  }
  const at = [0];
  for (let i = 1; i < pts.length; i++) at.push(at[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1], pts[i][2] - pts[i - 1][2]));
  return { pts, at, clear: at[1], all: at[at.length - 1], u: 0, pose: { rx: box.p.rx, ry: box.p.ry, s: box.p.s }, rz: rnd(-1.0, 1.0) };
}
function follow(b) {
  const r = b.route, d = r.u * r.all;
  let i = 1;
  while (i < r.at.length - 1 && r.at[i] < d) i++;
  const k = clamp((d - r.at[i - 1]) / Math.max(1e-6, r.at[i] - r.at[i - 1]));
  const q = [0, 1, 2].map((n) => lerp(r.pts[i - 1][n], r.pts[i][n], k));
  // How far along the bow it is: it straightens up, grows, and leans into the turn.
  const w = clamp((d - r.clear) / (r.all - r.clear)), e = w * w * (3 - 2 * w);
  Object.assign(b.p, { x: q[0], y: q[1], z: q[2], rx: lerp(r.pose.rx, 0, e), ry: lerp(r.pose.ry, 0, e), s: lerp(r.pose.s, 1, e), rz: 7 * Math.sin(Math.PI * w) * (1 - w) + r.rz * e });
  if (b.state === "rise" && d > r.clear) { b.state = "arrive"; active = b; }
}
async function arrive(b) {
  const my = epoch, ms = pace(1060);
  b.resolve = null;
  b.state = "rise";
  b.p = P();
  b.route = route(b);
  follow(b);
  b.px = b.p.x;
  b.py = b.p.y;
  snd.slide(0.26, 0.95, -0.35);
  snd.rustle(5, ms * 0.6, 0.09, 1);
  void tween(b.route, { u: 1 }, ms, E.glide).then(() => { b.route = null; });
  // The box gives a little as the bag is drawn out of it.
  void tween(box.p, { rz: -0.9, y: 71 }, ms * 0.22, E.flow).then(() => tween(box.p, { rz: 0, y: 74 }, ms * 0.6, E.flow));
  await want(`${b.card.info.id}-front`).ready;
  await want(`${b.card.info.back}-back`).ready;
  await wait(ms * 0.72);
  if (my !== epoch || active !== b) return;
  b.state = "sealed";
  grip = null;
  ptr.sx = ptr.x;
  ptr.sy = ptr.y;
  if (ptr.down) ptr.moved = 10;
  b.sealedAt = clock;
  // A press that came while the bag was on its way tears it.
  if (early && !ptr.down) void tearAlone(b, 420);
  early = false;
}

/** The next bag comes up a little in the box. */
function peek() {
  const n = bags[cur + 1];
  if (n?.state === "box") void tween(n, { rise: 0.16 }, pace(620), E.flow);
}

/** The card shows itself at the mouth, back first: whose back it is already tells something. */
function popCard(b) {
  const c = b.card, land = c.info.land;
  c.state = "pop";
  c.p = P(b.p.x, b.p.y + 0.5 * MM, { ry: 180, rz: (land ? -90 : 0) + b.p.rz, s: 1 });
  c.lipOn = 1;
  void tween(b, { open: 1 }, pace(420), E.flow);
}

/** A rare bag, torn: the room goes dark, the bag sinks a little, and its light stands up out of the mouth before anything
 * else does. */
async function pour(b, live) {
  const c = b.card, kind = c.info.signed ? "sign" : c.info.kind, g = glowOf(c.info), group = kind === "group";
  phase = "spot";
  spot = { card: c, group, sign: kind === "sign" };
  pressWaiters = [];
  early = eager = false;
  tempo = 0;
  // The first of a box, the group and a signed one take their time; later ones and the automatic run are brisker.
  haste = auto ? 1.4 : kind === "duo" && wides ? 1.2 : 1;
  if (c.info.land) wides += 1;
  hud.classList.add("dim");
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
async function settleRare(c) {
  void tween(scene, { spot: 0, toneAmt: 0, rays: 0 }, 760, E.flow);
  hud.classList.remove("dim");
  phase = "play";
  shown = null;
  tempo = 0;
  void collect(c, opened - 1);
  spot = null;
  await wait(260);
}

/** A card of one member comes out of its bag and turns over; a signed one unhurried, in its own light. False once the box
 * has been left. */
async function soloOut(b, live, grand = false) {
  const c = b.card, pc = grand ? (ms) => ms * 1.35 : pace;
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
  if (!grand) shown = c;
  void tween(c, { lipOn: 0 }, pc(200));
  // Over it goes, rising a little and leaning into the turn.
  void tween(c.p, grand ? { y: -14, s: 1.36 } : { y: -26, s: 1.2 }, pc(760), E.flow);
  void tween(c.p, { z: grand ? 130 : 90 }, pc(380), E.flow).then(() => tween(c.p, { z: grand ? 110 : 40 }, pc(420), E.flow));
  void tween(c.p, { rz: -3.2 }, pc(320), E.flow).then(() => tween(c.p, { rz: 0 }, pc(460), E.flow));
  void tween(c.p, { ry: 360 }, pc(740), E.flow);
  await wait(pc(330));
  if (!live()) return false;
  snd.flip(0.75, 1);
  c.sheen = -0.5;
  c.sheenAmt = grand ? 0.14 : 0.26;
  void tween(c, { sheen: 1.9 }, pc(1000), E.flow, pc(120));
  let written = true;
  if (grand) {
    // The pen is already on it as the face comes round.
    await wait(115);
    if (!live()) return false;
    written = write(c);
    void tween(scene, { rays: 0.10 }, 700, E.flow);
  }
  await wait(pc(420) - (grand ? 115 : 0));
  if (!live()) return false;
  c.p.ry = 0;
  return written;
}
/** The pen goes over the card; resolves once all of it is there. */
function write(c) {
  // What was pressed on the way here does not count: the writing would be over before it was seen.
  pressWaiters = [];
  early = eager = false;
  haste = auto ? 1.4 : 1;
  const sg = c.info.signed, since = clock;
  c.signT = 0;
  return new Promise((done) => {
    void tween(c, { signT: 1.02 }, sg.ms * 1.02, E.linear).then(() => done(true));
    // A press writes the rest at once.
    spot.write = () => {
      if (clock - since < 450 || spot.quick) return;
      spot.quick = true;
      void tween(c, { signT: 1.02 }, 320, E.flow).then(() => done(true));
    };
  });
}
async function revealSolo(b, live) {
  if (!await soloOut(b, live)) return;
  await hold(lerp(220, 40, tempo), auto ? 320 : 0);
  if (!live()) return;
  shown = null;
  void collect(b.card, opened - 1);
  await wait(pace(110));
}

/** A signed card comes up out of the gold, and is signed while it turns over. */
async function revealSigned(b, live) {
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
  await hold(360, auto ? 1000 : 0);
  if (live()) await settleRare(c);
}

/** Holds a card on show until the next press; a run of quick tears does not wait long. */
async function hold(least, autoMs) {
  const asked = pressed();
  await wait(least);
  if (autoMs) await Promise.race([asked, wait(autoMs)]);
  else if (!early && !(eager && ptr.down)) await asked;
  early = false;
  pressWaiters = [];
}

async function dropBag(b, k, ms = 460) {
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

async function collect(c, k) {
  c.state = "fly";
  letTurnGo(c);
  const at = railAt(k);
  if (RANK(c)) at.y -= 13;       // like a card drawn up out of the row
  const wide = c.info.land;
  const s = 98 / CARD_H;
  snd.slide(0.28, 1.2);
  // Across first, then down.
  void tween(c.p, { x: at.x }, pace(560), E.out);
  void tween(c.p, { rz: wide ? -90 : 0, s, z: 0, rx: 0, ry: 0 }, pace(560), E.flow);
  await tween(c.p, { y: at.y }, pace(560), E.flow);
  c.state = "rail";
  c.p.s = s;
  c.gleam = -0.6;
  void tween(c, { gleam: 2 }, 700, E.flow);
  snd.flip(0.28, 1.25, at.x / 480);
}

/* ---------------------------------------------------------------- a sideways card */
// Its light has said how many are on it. It comes up out of the bag, swings level and turns over; the colours it stood in
// go behind it, each on its own side.
async function revealWide(b, live) {
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
  await turnWide();
  if (!live()) return;
  haste = 1;
  early = false;
  await hold(group ? 500 : 320, auto ? (group ? 1100 : 700) : 0);
  if (live()) await settleRare(c);
}

async function turnWide() {
  const my = epoch, c = spot.card, group = spot.group;
  snd.slide(0.4, 0.9);
  void tween(c.p, { ry: 360, s: 1.6 }, 1250, E.flow);
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
  if (my !== epoch) return;
  c.p.ry = 0;
  shown = c;
}

/* ---------------------------------------------------------------- the whole box laid out */
function spreadPlan() {
  // The sideways ones on top, the rest in two rows under them, in the order they came.
  const wide = cards.filter((c) => c.info.land), tall = cards.filter((c) => !c.info.land).sort((a, b) => RANK(b) - RANK(a));
  const plan = new Map();
  const ww = Math.min(212, 860 / Math.max(1, wide.length) - 16), wh = ww * 54 / 86;
  wide.forEach((c, i) => plan.set(c, { x: (i - (wide.length - 1) / 2) * (ww + 16), y: -214 + (136 - wh) / 2, s: ww / CARD_H }));
  const rows = Math.ceil(tall.length / 8), per = Math.ceil(tall.length / rows);
  const th = Math.min(150, 330 / rows), tw = th * 54 / 86;
  tall.forEach((c, i) => {
    const r = Math.floor(i / per), n = r < rows - 1 ? per : tall.length - per * (rows - 1), k = i - r * per;
    plan.set(c, { x: (k - (n - 1) / 2) * (tw + 13), y: (wide.length ? -54 : -110) + r * (th + 14), s: th / CARD_H });
  });
  return plan;
}
async function finale() {
  const my = epoch;
  phase = "gather";
  setAuto(false);
  autoKey.classList.add("off");
  await thumbsReady;
  await wait(CALM ? 0 : 420);
  if (my !== epoch) return;
  countEl.classList.remove("on");
  // The empties are swept off the desk.
  snd.rustle(26, 620, 0.26, 0.7);
  for (const b of bags) {
    void tween(b.p, { x: b.p.x + 420, y: b.p.y + rnd(-30, 60), rz: b.p.rz + rnd(20, 70) }, 860, E.flow, rnd(0, 220));
  }
  void tween(box.p, { x: -700 }, 820, E.flow, 120);
  await wait(CALM ? 0 : 560);
  if (my !== epoch) return;
  const plan = spreadPlan();
  for (const b of bags) b.state = "gone";
  // The plain ones first, then the rare, the rarest last.
  const turnOf = [...cards].sort((a, b) => RANK(a) - RANK(b)), plain = turnOf.filter((c) => !RANK(c)).length;
  const after = (c) => { const i = turnOf.indexOf(c); return i < plain ? i * 30 : plain * 30 + 160 + (i - plain) * 170; };
  cards.forEach((c, i) => {
    const to = plan.get(c), late = after(c);
    c.state = "spread";
    c.home = { ...to };
    void tween(c.p, { x: to.x, s: to.s, rz: 0 }, 900, E.flow, late);
    void tween(c.p, { y: to.y }, 900, E.out, late);
    void wait(late + 620).then(() => { if (my !== epoch) return; snd.flip(0.32, 1.1 + i * 0.012, to.x / 480); c.gleam = -0.6; void tween(c, { gleam: 2 }, 520, E.out); });
  });
  await wait(after(turnOf[COUNT - 1]) + 940);
  if (my !== epoch) return;
  box.on = false;
  haste = 1;
  phase = "end";
  againKey.classList.remove("off");
}
async function leave() {
  const my = epoch;
  phase = "leaving";
  againKey.classList.add("off");
  if (inspecting) await putBack();
  snd.slide(0.6, 0.9);
  cards.forEach((c, i) => void tween(c.p, { y: c.p.y - 620, rz: rnd(-6, 6) }, 720, E.flow, i * 12));
  await wait(900);
  return my;
}
/** A card of the spread brought up close. */
function tapEnd(x, y) {
  for (const c of cards) {
    const w = (c.info.land ? CARD_H : CARD_W) * c.p.s / 2, h = (c.info.land ? CARD_W : CARD_H) * c.p.s / 2;
    if (Math.abs(x - c.p.x) < w && Math.abs(y - c.p.y) < h) return void takeUp(c);
  }
}
async function takeUp(c) {
  inspecting = c;
  phase = "taking";
  const my = epoch;
  await Promise.all([want(`${c.info.id}-front`).ready, want(`${c.info.back}-back`).ready]);
  if (my !== epoch) return;
  c.state = "inspect";
  shown = c;
  snd.slide(0.5, 1.1);
  againKey.classList.add("off");
  scene.lights = PALE;
  void tween(scene, { spot: 0.82 }, 560, E.flow);
  await tween(c.p, { x: 0, y: -8, z: 120, s: c.info.land ? 1.6 : 1.28, rz: 0 }, 620, E.flow);
  phase = "end";
}
async function putBack() {
  const c = inspecting;
  if (!c || phase === "taking") return;
  phase = "taking";
  inspecting = null;
  shown = null;
  letTurnGo(c);
  snd.slide(0.4, 1.2);
  void tween(scene, { spot: 0 }, 560, E.flow);
  await tween(c.p, { x: c.home.x, y: c.home.y, z: 0, s: c.home.s, rx: 0, ry: 0 }, 620, E.flow);
  c.state = "spread";
  if (phase === "taking") { phase = "end"; againKey.classList.remove("off"); }
}

/* ---------------------------------------------------------------- each frame */
function update(dt) {
  advance(dt * haste);
  ptr.vx *= Math.exp(-dt / 90);
  ptr.vy *= Math.exp(-dt / 90);
  if (box.sway) {
    const t = clock / 1000;
    box.p.ry = 26 + 7 * Math.sin(t * 0.8) + (ptr.inside ? ptr.x / 480 * 12 : 0);
    box.p.rx = -14 + 2.5 * Math.sin(t * 0.63 + 1) + (ptr.inside ? -ptr.y / 320 * 5 : 0);
    // The lid stirs now and then.
    if (phase === "intro" && box.p.y > -20) box.lid = 90 + 5 * Math.max(0, Math.sin(t * 2.1)) ** 6;
  }
  for (const b of bags) {
    if (b.route) follow(b);
    if (b.state === "sealed" && b === active) {
      if (b.drive) pull(b, b.drive.q, 0.65);
      const idle = clock - (b.sealedAt ?? clock);
      if (b.state === "sealed" && !b.n && idle > 900 && !ptr.down) { const k = ((idle - 900) % 2100) / 900; b.hint = k < 1 ? -0.25 + k * 1.5 : -2; }
    }
    if (b.drive && b.torn) b.drive = null;
    // The flap rolls up as it comes away, and goes on over once it is free.
    b.curlV += ((b.torn ? 3.1 : 1.0 + 1.6 * clamp(b.q * 1.2)) - b.curl) * dt * (b.torn ? 0.00026 : 0.00011);
    b.curlV *= Math.exp(-dt / (b.torn ? 32 : 62));
    b.curl = clamp(b.curl + b.curlV * dt, 0.2, 3.12);
    b.rad += ((b.torn ? 0.02 : lerp(0.62, 0.36, b.q)) - b.rad) * (1 - Math.exp(-dt / (b.torn ? 80 : 140)));
    const want2 = b.state === "sealed" && ptr.down ? -b.strain * 2.2 : 0;
    b.tugV += (want2 - b.tug) * dt * 0.0016;
    b.tugV *= Math.exp(-dt / 55);
    b.tug += b.tugV * dt;
    // Soft film: it bows with the way it is moved and comes to rest with a small sway.
    const hx = (b.p.x - (b.px ?? b.p.x)) / Math.max(1, dt), hy = (b.p.y - (b.py ?? b.p.y)) / Math.max(1, dt), loose = b.torn ? 1 : 0.45;
    b.px = b.p.x;
    b.py = b.p.y;
    for (const [k, v, to] of [["bx", "vbx", clamp(hx * 15, -20, 20) * loose], ["by", "vby", clamp(hy * 15, -20, 20) * loose]]) {
      b[v] += ((to - b[k]) * 0.00012 - b[v] * 0.0075) * Math.min(dt, 32);
      b[k] += b[v] * Math.min(dt, 32);
    }
    const inHand = b === active && b.state === "sealed" && ptr.down;
    b.lift2 += ((inHand ? 5 * b.q + 9 * b.strain * clamp(b.q * 8) : b.torn ? 0 : 3 * b.q) - b.lift2) * (1 - Math.exp(-dt / 130));
    const rip = b.torn ? 3.2 : 2 + 2.4 * b.q + clamp(Math.abs(ptr.vy) * 1.2, 0, 2) * (inHand ? 1 : 0);
    b.vw += ((rip - b.wave) * 0.00010 - b.vw * 0.008) * Math.min(dt, 32);
    b.wave += b.vw * Math.min(dt, 32);
    b.shown += (b.q - b.shown) * (1 - Math.exp(-dt / 22));
    // The light swells behind the hand, and goes out once the bag is let go of.
    const lit = b.state === "sealed" || b.state === "torn" ? 0.18 * smooth(0, 0.1, b.q) + 0.82 * smooth(0.05, 1, b.q) : 0;
    b.glow += (lit - b.glow) * (1 - Math.exp(-dt / (lit > b.glow ? 90 : 190)));
  }
  {
    // While it is torn, the desk already goes a little dark and takes the colours.
    const a = active && (active.state === "sealed" || active.state === "torn") ? active : null, g = a && glowOf(a.card.info), k = 1 - Math.exp(-dt / 170);
    scene.dusk += ((a ? g.dusk * smooth(0.15, 1, a.glow) : 0) - scene.dusk) * k;
    scene.warm += ((a ? g.warm * 0.7 * smooth(0.1, 1, a.glow) : 0) - scene.warm) * k;
  }
  if (turn.card && !turn.held) {
    const settle = (k, v, to, ms) => { turn[v] += ((to - turn[k]) * 0.00006 - turn[v] * 0.0135) * ms; turn[k] += turn[v] * ms; };
    for (let left = dt; left > 0; left -= 8) { settle("yaw", "vy", turn.to, Math.min(8, left)); settle("pitch", "vp", 0, Math.min(8, left)); }
  }
  // Cards and the bag in hand lean toward the pointer.
  for (const c of cards) {
    const held = c === shown || (spot?.sign && c === spot.card);
    const near = held && !turn.held, wide = c === inspecting ? 1 : 0;
    const tx = near && ptr.inside ? clamp(ptr.x / 300, -1, 1) : near ? 0.5 * Math.sin(clock / 1300) : 0;
    const ty = near && ptr.inside ? clamp((ptr.y - c.p.y) / 260, -1, 1) : near ? 0.5 * Math.sin(clock / 1700 + 1) : 0;
    const k = 1 - Math.exp(-dt / 90);
    c.amp += ((wide ? 26 : 18) - c.amp) * k;
    if (c.info.signed) {
      const path = c.info.signed.tip, f = clamp(c.signT) * (path.length - 1), i = Math.floor(f), from = path[i], to = path[Math.min(path.length - 1, i + 1)];
      const busy = c.signT >= 0 && c.signT < 1.01 && from;
      if (busy) c.tip = to && Math.hypot(to[0] - from[0], to[1] - from[1]) < 90 ? [lerp(from[0], to[0], f - i), lerp(from[1], to[1], f - i)] : from;
      c.tipAmt += ((busy ? 1 : 0) - c.tipAmt) * (1 - Math.exp(-dt / (busy ? 60 : 160)));
    }
    c.float += ((held ? 1 : 0) - c.float) * (1 - Math.exp(-dt / 400));
    c.tiltX += (tx - c.tiltX) * k;
    c.tiltY += (ty - c.tiltY) * k;
  }
  if (active) {
    const on = active.state === "sealed" || active.state === "arrive";
    const k = 1 - Math.exp(-dt / 160);
    active.float = (active.float ?? 0) + ((on ? 1 : 0) - (active.float ?? 0)) * (1 - Math.exp(-dt / 400));
    active.leanX = (active.leanX ?? 0) + ((on && ptr.inside ? clamp(ptr.x / 260, -1, 1) : on ? 0.55 * Math.sin(clock / 1500) : 0) - (active.leanX ?? 0)) * k;
    active.leanY = (active.leanY ?? 0) + ((on && ptr.inside ? clamp(ptr.y / 260, -1, 1) : on ? 0.4 * Math.sin(clock / 1900 + 2) : 0) - (active.leanY ?? 0)) * k;
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
}

/* ---------------------------------------------------------------- drawing */
let vp = G.ident();
const lamp = () => [ptr.inside ? ptr.x : 180 * Math.sin(clock / 1400), ptr.inside ? ptr.y : -120 + 60 * Math.sin(clock / 1900), 230];
const roomShift = () => [(ptr.inside ? ptr.x / 480 : 0.4 * Math.sin(clock / 2300)) * 0.05, (ptr.inside ? ptr.y / 320 : 0.3 * Math.sin(clock / 2900)) * 0.035];
const clearDepth = () => gl.clear(gl.DEPTH_BUFFER_BIT);

function flat(prog, model, dim, values = {}, texture = null, rect = [0, 0, 1, 1]) {
  prog.use();
  if (texture) prog.tex("u_tex", 0, texture);
  prog.set({ u_vp: vp, u_model: model, u_dim: dim, u_rect: rect, ...values });
  mesh.quad.draw();
}
function shadow(x, y, w, h, rz, alpha, grow = 1.6) {
  gl.disable(gl.DEPTH_TEST);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  flat(progs.shadow, G.pose(P(x, y, { rz })), [w * grow, h * grow], { u_alpha: alpha }, tex.shadow);
}
function foil(b, p, piece, o = {}) {
  const f = progs.foil;
  f.use();
  f.tex("u_room", 1, tex.room);
  f.set({
    u_vp: vp, u_model: G.pose(p), u_size: BAG, u_flap: FLAP, u_piece: piece, u_q: b.shown, u_grip: b.gx, u_rad: b.rad * FLAP, u_curl: b.curl, u_open: b.open, u_air: b.air, u_bend: [b.bx, b.by], u_lift: b.lift2, u_wave: b.wave, u_crush: b.crush,
    u_glow: b.glow > 0.003 ? b.glow * glowOf(b.card.info).power : 0, ...(b.glow > 0.003 ? lightU(lightNow(b)) : lightU(PALE)),
    u_cut: o.cut ?? 0, u_closed: piece === 0 && b.q <= 0 && b.shown < 0.002 ? 1 : 0, u_full: b.full, u_seed: b.seed, u_flip: b.flip, u_room_shift: roomShift(), u_lamp: lamp(), u_lit: o.lit ?? b.lit, u_hint: b.hint, u_strain: b.q > 0 ? b.strain : 0,
  });
  (piece === 1 ? mesh.flap : o.low ? mesh.low : mesh.fine).draw();
}
const solid = () => { gl.enable(gl.DEPTH_TEST); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); };

function drawCard(c, p) {
  const f = full.get(`${c.info.id}-front`), bk = full.get(`${c.info.back}-back`);
  if (!f?.base || !bk?.base) return;
  f.used = bk.used = clock;
  const dim = c.info.land ? [CARD_H, CARD_W] : [CARD_W, CARD_H];
  const mine = turn.card === c;
  // Leaning and turning by hand go about the screen's axes, over the card's own pose.
  const leanY = c.tiltX * c.amp + (mine ? turn.yaw : 0), leanX = -c.tiltY * c.amp * 0.85 + (mine ? turn.pitch : 0);
  const yaw = p.ry + leanY, pitch = p.rx + leanX;
  const y = p.y + 2.2 * Math.sin(clock / 1200) * c.float;
  const m = [G.move(p.x, y, p.z), G.rotX(leanX * RAD), G.rotY(leanY * RAD), G.rotZ(p.rz * RAD), G.rotY(p.ry * RAD), G.rotX(p.rx * RAD), G.scale(p.s, p.s, p.s)].reduce(G.mul);
  // The light stays where it is while the card turns under it.
  const half = (a) => ((a + 90) % 180 + 180) % 180 - 90;
  const light = [clamp(0.5 + 1.35 * Math.sin(half(yaw) * RAD), -0.25, 1.25), clamp(0.46 - 1.35 * Math.sin(half(pitch) * RAD), -0.25, 1.25)];
  // Which of its sides face the eye.
  const faces = (nx, ny, nz, x, y2, z) => nx * -x + ny * -y2 + nz * (G.DIST - z);
  const side = (col, r) => { const k = 1 / p.s; const n = [m[col] * k, m[col + 1] * k, m[col + 2] * k]; return [n, (d) => faces(n[0] * d, n[1] * d, n[2] * d, m[12] + n[0] * d * r, m[13] + n[1] * d * r, m[14] + n[2] * d * r) > 0]; };
  const rims = [side(0, dim[0] * p.s / 2)[1](-1), side(0, dim[0] * p.s / 2)[1](1), side(4, dim[1] * p.s / 2)[1](-1), side(4, dim[1] * p.s / 2)[1](1)];
  const r = progs.rim;
  r.use();
  r.tex("u_noise", 2, tex.noise);
  rims.forEach((on, k) => {
    if (!on) return;
    r.set({ u_vp: vp, u_model: m, u_dim: dim, u_bend: c.bend, u_thick: THICK, u_face: 0, u_rim: k + 1, u_lit: 1, u_lip: c.lip, u_lipOn: c.lipOn });
    mesh.strip.draw();
  });
  const [, sees] = side(8, THICK * p.s / 2);
  const face = sees(1) ? 1 : sees(-1) ? -1 : 0;
  if (!face) return;
  const g = progs.card;
  g.use();
  g.tex("u_base", 0, f.base);
  g.tex("u_mat", 1, f.mat);
  g.tex("u_noise", 2, tex.noise);
  g.tex("u_baseB", 3, bk.base);
  g.tex("u_matB", 4, bk.mat);
  const sg = c.info.signed;
  g.tex("u_sign", 5, sg ? sg.tex : tex.noise);
  g.set({
    u_vp: vp, u_model: m, u_dim: dim, u_size: c.info.size, u_light: light, u_scale: c.info.size[0] / Math.max(1, dim[0] * p.s * view.px), u_on: 1,
    u_foilDark: c.info.foil.dark, u_foilLit: c.info.foil.lit, u_printDark: c.info.print.dark, u_printLit: c.info.print.lit, u_silverDark: SILVER.dark, u_silverLit: SILVER.lit,
    u_bend: c.bend, u_thick: THICK, u_face: face, u_rim: 0, u_lit: 1, u_lip: c.lip, u_lipOn: c.lipOn, u_sheen: c.sheen, u_sheenAmt: c.sheenAmt, u_tone: c.info.tones[0], u_flash: c.flash, u_signBox: sg ? sg.box : NONE, u_signT: c.signT, u_signGleam: c.gleamInk, u_tip: [c.tip[0], c.tip[1], c.tipAmt],
    u_lipLight: c.lipLight, ...lightU(c.info.light),
  });
  mesh.card.draw();
}
function drawThumb(c, lit) {
  const dim = c.info.land ? [CARD_H, CARD_W] : [CARD_W, CARD_H];
  const t = THICK * c.p.s, sg = c.info.signed;
  progs.thumb.use();
  progs.thumb.tex("u_sign", 1, sg ? sg.tex : tex.noise);
  flat(progs.thumb, G.pose({ ...c.p, x: c.p.x + t * 0.35, y: c.p.y + t }), dim, { u_lit: lit, u_gleam: -9, u_solid: 1, u_signBox: NONE }, tex.atlas, c.info.rect);
  flat(progs.thumb, G.pose(c.p), dim, { u_lit: lit, u_gleam: c.gleam, u_solid: 0, u_signBox: sg ? sg.uv : NONE }, tex.atlas, c.info.rect);
}
const NONE = [0, 0, 0, 0], FOLD = 1.7 * MM;   // how far round a fold in the board goes
function panel(m, dim, o = {}) {
  progs.box.set({ u_vp: vp, u_model: m, u_dim: dim, u_print: o.print ?? [0, 0, 1, 1], u_inked: o.print ? 1 : 0, u_lit: o.lit, u_lamp: lamp(), u_dark: o.dark ?? 0, u_edge: o.edge ?? 0, u_fold: o.fold ?? NONE, u_radius: o.fold ? FOLD : 0, u_bow: o.fold ? 0.045 : 0, u_corner: o.corner ?? [0, 0] });
  (o.fold ? mesh.board : mesh.quad).draw();
}
const T = (x, y, z) => G.move(x, y, z), M = (...a) => a.reduce(G.mul);
/** A piece of board with its cut edges; `edges` names the sides that show: t, b, l, r. */
function slab(m, w, h, edges, o) {
  const t = BOARD, q = Math.PI / 2;
  panel(m, [w, h], o);
  panel(M(m, T(0, 0, -t)), [w, h], { lit: o.lit, corner: o.corner });
  const e = { lit: o.lit, edge: 1 };
  // Cut edges stop short of rounded corners and of the folds.
  const [ct, cb] = o.corner ?? [0, 0], cut = FOLD * 0.3, y0 = -h / 2 + (o.fold?.[2] ? cut : ct), y1 = h / 2 - (o.fold?.[3] ? cut : cb);
  if (edges.includes("t")) panel(M(m, T(0, -h / 2, -t / 2), G.rotX(q)), [w - 2 * ct, t], e);
  if (edges.includes("b")) panel(M(m, T(0, h / 2, -t / 2), G.rotX(-q)), [w - 2 * cb, t], e);
  if (edges.includes("l")) panel(M(m, T(-w / 2, (y0 + y1) / 2, -t / 2), G.rotY(-q)), [t, y1 - y0], e);
  if (edges.includes("r")) panel(M(m, T(w / 2, (y0 + y1) / 2, -t / 2), G.rotY(q)), [t, y1 - y0], e);
}
function boxParts(lit, part) {
  const [w, h, d] = BOX, t = BOARD, q = Math.PI / 2, gap = 1.2;
  const m = G.pose(box.p);
  const g = progs.box;
  g.use();
  g.tex("u_ink", 0, tex.ink);
  g.tex("u_noise", 1, tex.noise);
  const edge = { lit, edge: 1 };
  if (part !== "front") {
    const side = [780 / 1280, 0, 1180 / 1280, 1];
    // Walls: the printed face, then the board's inside, set in by its thickness. Nothing shares a plane.
    const back = M(m, T(0, 0, -d / 2), G.rotY(Math.PI));
    const all = [1, 1, 1, 1];
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
    const shut = clamp(box.flaps / 90), fl = 13 * MM, fw = d - 4 * t - 8;
    for (const s of [-1, 1]) {
      const f = M(m, T(s * (w / 2 - gap * shut), -h / 2 + (t + gap) * shut, 0), G.rotY(s * q), G.rotX(box.flaps * RAD), T(0, -fl / 2, 0));
      slab(f, fw, fl, "tlr", { lit, fold: [0, 0, 0, 1], corner: [5 * MM, 0] });
    }
    // The lid reaches the inside of the front wall, and its tongue goes down behind that.
    const lw = w - 2 * FOLD * 0.3, ld = d - t - gap, tw = w - 2 * t - 8, th = 11 * MM;
    const lid = M(m, T(0, -h / 2, -d / 2), G.rotX(box.lid * RAD), T(0, ld / 2, 0));
    slab(lid, lw, ld, "lr", { lit, fold: [0, 0, 1, 1] });
    panel(M(lid, T(0, ld / 2, -t / 2), G.rotX(-q)), [lw, t], edge);
    slab(M(lid, T(0, ld / 2, 0), G.rotX(box.tuck * RAD), T(0, th / 2, 0)), tw, th, "blr", { lit, fold: [0, 0, 1, 0], corner: [0, 6 * MM] });
  }
  if (part !== "back") {
    const front = M(m, T(0, 0, d / 2));
    panel(M(front, T(0, 0, -t)), [w - 2 * gap, h], { lit });
    panel(front, [w, h], { lit, fold: [1, 1, 0, 1], print: [0, 0, 755 / 1280, 1] });
    panel(M(m, T(0, -h / 2, d / 2 - t / 2), G.rotX(q)), [w - FOLD * 0.6, t], edge);
  }
}
/** The first of the light is pale, whoever is in there; its colours part as the flap goes up. */
function lightNow(b) {
  const k = smooth(0.10, 0.46, b.glow);
  return k >= 1 ? b.card.info.light : b.card.info.light.map((t) => t.map((v, i) => lerp(PALE[0][i], v, k)));
}
const breath = (b) => 1 + 0.05 * Math.sin(clock / 640 + b.seed);
/** Over the bag: light adds to what lies under it, and colours it. */
function glowing(prog, model, dim, values) {
  gl.disable(gl.DEPTH_TEST);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  flat(prog, model, dim, { u_time: clock / 1000, ...values });
  solid();
}
function slit(b, p, k = 1) {
  const amt = b.glow * glowOf(b.card.info).power * breath(b) * k;
  if (amt < 0.004) return;
  const w = BAG[0] * 2.0, h = 340, top = 110;
  glowing(progs.slit, M(G.pose(p), T(0, -BAG[1] / 2 - top + h / 2, 6)), [w, h], { u_bag: [BAG[0], top], u_flap: FLAP, u_q: b.shown, u_grip: b.gx, u_rad: b.rad * FLAP, u_amt: amt, ...lightU(lightNow(b)) });
}
function beam(b, p, k = 1) {
  const g = glowOf(b.card.info), amt = b.beam * g.power * breath(b) * k;
  if (amt < 0.004) return;
  const w = 940, h = 600, foot = 70;
  glowing(progs.beam, M(G.pose(p), T(0, -BAG[1] / 2 + foot - h / 2, 2)), [w, h], { u_mouth: 1 - foot / h, u_half: BAG[0] * 0.455, u_deep: g.deep, u_reach: g.reach * (0.45 + 0.55 * b.beam), u_amt: amt, ...lightU(b.card.info.light) });
}
function drawBag(b, o = {}) {
  const p = o.p ?? b.p;
  if (!b.torn) {
    foil(b, p, 0, o);
    if (b.q > 0) { foil(b, p, 1, o); slit(b, p); }
    return;
  }
  // Open: what stands up of the flap is behind everything, then the dark inside, the card, the near side, and over it
  // whatever of the flap has not gone up yet.
  foil(b, p, 1, { ...o, cut: 1 });
  clearDepth();
  foil(b, p, 3, o);
  // Most of the light stands behind the card, a little of it before.
  beam(b, p, 0.92);
  if (o.between) { gl.disable(gl.DEPTH_TEST); o.between(); gl.enable(gl.DEPTH_TEST); }
  clearDepth();
  foil(b, p, 2, o);
  clearDepth();
  foil(b, p, 1, { ...o, cut: 2 });
  beam(b, p, 0.26);
  slit(b, p, 1 - b.beam);
}

// Particles: one buffer, filled each frame.
const bitVao = gl.createVertexArray(), bitBuf = gl.createBuffer(), cornerBuf = gl.createBuffer();
gl.bindVertexArray(bitVao);
gl.bindBuffer(gl.ARRAY_BUFFER, cornerBuf);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-0.5, -0.5, -0.5, 0.5, 0.5, -0.5, 0.5, 0.5]), gl.STATIC_DRAW);
gl.enableVertexAttribArray(0);
gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
gl.bindBuffer(gl.ARRAY_BUFFER, bitBuf);
for (const [l, at] of [[1, 0], [2, 16]]) {
  gl.enableVertexAttribArray(l);
  gl.vertexAttribPointer(l, 4, gl.FLOAT, false, 32, at);
  gl.vertexAttribDivisor(l, 1);
}
gl.bindVertexArray(null);
function drawBits(kind) {
  const list = fx.filter((f) => f.life >= 0 && (kind ? f.kind > 0 : !f.kind));
  if (!list.length) return;
  const data = new Float32Array(list.length * 8);
  list.forEach((f, i) => {
    const k = f.life / f.max, fade = f.kind ? Math.min(1, f.life / 220) * (1 - k) ** 1.5 : 1;
    data.set([f.x, f.y, f.size * (f.kind ? 1 : 1 - 0.5 * k), f.kind, f.c[0] * fade, f.c[1] * fade, f.c[2] * fade, f.spin], i * 8);
  });
  progs.bits.use();
  progs.bits.set({ u_vp: vp });
  gl.disable(gl.DEPTH_TEST);
  if (kind) gl.blendFunc(gl.ONE, gl.ONE);
  else gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.bindVertexArray(bitVao);
  gl.bindBuffer(gl.ARRAY_BUFFER, bitBuf);
  gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
  gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, list.length);
  gl.bindVertexArray(null);
}

function wash(amount) {
  if (amount < 0.005) return;
  gl.disable(gl.DEPTH_TEST);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  flat(progs.wash, G.ident(), [view.w + 60, view.h + 60], { u_color: [...scene.flashTone, amount], u_round: 0.75 });
}
function draw() {
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.enable(gl.BLEND);
  gl.depthFunc(gl.LEQUAL);
  gl.clearColor(0.09, 0.07, 0.11, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  vp = G.camera(view.w, view.h);
  gl.disable(gl.DEPTH_TEST);
  const dark = Math.max(scene.spot, scene.dusk);
  progs.desk.use();
  progs.desk.tex("u_noise", 1, tex.noise);
  flat(progs.desk, G.ident(), [view.w + 60, view.h + 60], { u_view: [view.w, view.h], u_spot: dark, u_toneAmt: Math.max(scene.toneAmt, scene.warm), u_lampAt: [lamp()[0], lamp()[1]], ...lightU(scene.lights) });
  const dim = 1 - 0.72 * dark, inDark = 1 - 0.52 * dark;
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

  // The heap of empties.
  for (const b of bags) {
    if (b.state === "heap") shadow(b.p.x + 5, b.p.y + 8, BAG[0] * b.p.s, BAG[1] * b.p.s, b.p.rz, 0.30 * dim);
  }
  for (const b of bags) {
    if (b.state === "heap") { solid(); clearDepth(); foil(b, b.p, 1, { lit: dim * 0.9 }); foil(b, b.p, 3, { low: true, lit: dim * 0.9 }); clearDepth(); foil(b, b.p, 2, { low: true, lit: dim * 0.9 }); }
  }

  // The box, and the bags while they are in it or coming out of it.
  if (box.on) {
    const s = box.p.s;
    const shY = box.p.y + BOX[1] * s * 0.5 - 4;
    const lift = clamp((box.p.y + 6) / -700);
    shadow(box.p.x + 6, shY, BOX[0] * s * (1.15 + 0.3 * lift), BOX[2] * s * 0.8, 0, (0.55 - 0.45 * lift) * dim * (phase === "intro" ? 1 : 0.8), phase === "intro" ? 1.9 : 1.5);
    solid();
    clearDepth();
    boxParts(box.lit * dim, "back");
    const rising = bags.filter((b) => b.state === "rise" || (b.state === "box" && box.lid > 100));
    for (const b of rising) {
      const at = riseAt(b);
      foil(b, b.route ? b.p : P(at[0], at[1], { z: at[2], rx: box.p.rx, ry: box.p.ry, s: box.p.s }), 0, { low: true, lit: dim });
    }
    boxParts(box.lit * dim, "front");
  }

  // What has been opened, along the bottom or laid out.
  const rail = cards.filter((c) => c.state === "rail" || c.state === "spread");
  for (const c of rail) {
    const w = (c.info.land ? CARD_H : CARD_W) * c.p.s, h = (c.info.land ? CARD_W : CARD_H) * c.p.s;
    shadow(c.p.x + 3, c.p.y + 6, w, h, c.p.rz, 0.34 * dim, 1.5);
    gl.disable(gl.DEPTH_TEST);
    drawThumb(c, dim);
  }

  // A bag on its way to the heap.
  for (const b of bags) {
    if (b.state !== "falling") continue;
    const c = b.card;
    const between = c.state === "pop" ? () => { c.lip = b.p.y - BAG[1] / 2 + 10; c.lipLight = b.beam * glowOf(c.info).power; drawCard(c, c.p); } : null;
    solid();
    clearDepth();
    drawBag(b, { between, lit: lerp(inDark, dim, b.fade) });
  }

  // The bag in hand.
  if (active && active.state !== "falling" && active.state !== "heap" && active.state !== "rise") {
    const b = active;
    const p = { ...b.p, y: b.p.y + b.tug + 2.6 * Math.sin(clock / 1050) * (b.float ?? 0), x: b.p.x, ry: b.p.ry + (b.leanX ?? 0) * 13, rx: b.p.rx - (b.leanY ?? 0) * 11 };
    shadow(p.x + 10 - (b.leanX ?? 0) * 12, p.y + 26, BAG[0] * p.s, BAG[1] * p.s, p.rz, 0.5, 1.55);
    solid();
    clearDepth();
    const c = b.card;
    const between = c.state === "pop" ? () => {
      c.lip = p.y - BAG[1] / 2 + 10;
      c.lipLight = b.beam * glowOf(c.info).power;
      drawCard(c, c.p);
    } : null;
    drawBag(b, { p, between, lit: inDark });
  }

  // Light for a card that earned it.
  if (scene.rays > 0.01) {
    gl.disable(gl.DEPTH_TEST);
    gl.blendFunc(gl.ONE, gl.ONE);
    flat(progs.rays, G.pose(P(scene.rayAt.x, scene.rayAt.y)), [1500, 1500], { u_time: clock / 1000, u_amt: scene.rays, ...lightU(scene.lights) });
  }
  // The burst lies behind the card, and over it for a blink only.
  wash(scene.flash * 0.7);
  for (const c of cards) {
    if (c.state !== "out" && c.state !== "fly" && c.state !== "inspect") continue;
    const w = (c.info.land ? CARD_H : CARD_W) * c.p.s, h = (c.info.land ? CARD_W : CARD_H) * c.p.s;
    const turn = Math.abs(Math.cos(c.p.ry * RAD)), open = Math.abs(Math.cos(c.p.rx * RAD));
    shadow(c.p.x + 8 - c.tiltX * 10, c.p.y + 24, w * (0.35 + 0.65 * turn), h * (0.2 + 0.8 * open), c.p.rz, 0.5 * (1 - 0.4 * dark), 1.55);
    gl.enable(gl.DEPTH_TEST);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    clearDepth();
    drawCard(c, c.p);
  }
  drawBits(1);
  wash(scene.flash ** 4 * 0.85);
}

let last = 0;
function frame(now) {
  const dt = Math.min(48, now - (last || now));
  last = now;
  update(dt);
  draw();
  requestAnimationFrame(frame);
}
fit();
snd.load();
reset();
if (MANUAL) {
  // For checks: the clock only moves when told to.
  window.demo = {
    async step(ms, slice = 16) { for (let t = 0; t < ms; t += slice) { update(slice); await null; await null; await null; await null; } draw(); gl.finish(); },
    down: (x, y) => onDown(x, y, clock), move: (x, y) => onMove(x, y, clock), up: onUp,
    state: () => ({ phase, cur, opened, active: active && { i: active.i, state: active.state, q: active.q, n: active.n, card: active.card.info.id }, shown: shown?.info.id, spot: spot?.card.info.id ?? null, tempo, fx: fx.length, deal: cards.map((c) => c.info.id), err: gl.getError() }),
    ready: () => Promise.all([thumbsReady, ...[...full.values()].map((f) => f.ready)]),
    bags: () => bags, cards: () => cards, scene,
  };
} else requestAnimationFrame(frame);
document.documentElement.dataset.ready = "1";
