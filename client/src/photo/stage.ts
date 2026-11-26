// The stage a photocards' page stands on: the key visual of its series, on a canvas of its own under the whole panel.
// It comes up out of the page's paper as an instant photo does, and is seen by itself then, over the whole panel. Behind
// the page it lies beside the sidebar, out of focus, and light gets in at its edges until it is paper again. The focus
// goes over from one picture of it to the next, each more blurred (scripts/photocards/stage.py). It moves with the
// pointer by how near everything in it is; lamps, dust and a glossy floor are added to it here.
// One canvas for every visit, taken down a while after the last. Frames are drawn while something moves; what only
// drifts (lamps, dust) is drawn at half the rate, and comes to rest when nobody has been there for a while.
import type { StageArt, StageLook } from "./art";
import { grid, picture, startProgram, texture, type GL, type Picture, type Vec2, type Vec3, type Vec4 } from "./gl";
import { clamp, lerp, smooth } from "./math";
import { STAGE_FS, STAGE_VS } from "./shaders";
import { createTimeline, E, type Ease, type Numbers } from "./time";

/** What can be moved, 0 to 1 unless said otherwise. */
export interface StageState {
  /** 0: the members are in focus, 1: as far out of it as it goes. */
  focus: number;
  /** How far it is shaded where words lie on it. */
  veil: number;
  /** How far it moves with the pointer; 1 as behind the page. */
  play: number;
  /** How much nearer the lens is; things come up by how near they are. */
  dolly: number;
  /** How bright the lamps' beams are. */
  lamps: number;
  /** How far it has come up out of the paper. */
  dev: number;
  /** How far light gets in at its edges; 1 as behind the page. */
  leak: number;
  /** 0: beside the sidebar, 1: over the whole panel. */
  wide: number;
}
/** Where the page's things are, in CSS pixels from the host's corner. */
export interface StageLayout {
  /** How wide the sidebar is, that lies over the left. */
  side: number;
  /** The page's paper. */
  paper: Vec3;
  /** Where the box stands, and CSS pixels to a design unit there; null where it stands on nothing of this. */
  foot: { x: number; y: number; css: number } | null;
  /** The title. */
  title: { x: number; y: number; w: number; h: number } | null;
}
/** What the lamps do: `turns` 1 one of them at a time, 2 two, 3 all. */
export interface StageLight { tones: readonly Vec3[]; turns: 1 | 2 | 3 }

export interface Stage {
  /** Draws in [host]. */
  mount(host: HTMLElement): void;
  /** Leaves its host. */
  release(): void;
  /** The key visual is there to be drawn; false when it could not be loaded. */
  load(art: StageArt): Promise<boolean>;
  /** The series on show; another one fades over. */
  show(art: StageArt): void;
  /** It can be seen. */
  seen(on: boolean): void;
  layout(to: StageLayout): void;
  /** Where the pointer is, -1 to 1 from the middle either way; null while it is not here. */
  pointer(at: Vec2 | null): void;
  set(state: Partial<StageState>): void;
  to(state: Partial<StageState>, ms: number, ease?: Ease, delay?: number): Promise<void>;
  /** The lamps' colours; null for the stage's own light. */
  light(to: StageLight | null): void;
  /** Its first picture is on the screen. */
  readonly up: Promise<void>;
}

/** How wide the key visual is, in widths of the page and of the whole panel, and which part of it lies in the middle. */
const SPAN = { page: 1.12, whole: 1.06 }, MIDDLE = { page: 0.49, whole: 0.5 };
/** It is paper from this far above the box's foot, in design units; from here down, in heights, where there is no box. */
const LOW = 34, LOW_AT = 0.64;
/** The floor begins this far down the picture. */
const FLOOR_AT = 0.963;
/** How far the pointer moves what is nearest against what is farthest, in parts of the picture. */
const PLAY: Vec2 = [0.0135, 0.011];
/** More out of focus than this it is drawn at one device pixel to a CSS pixel. */
const SOFT = 0.45;
/** It drifts for this long after somebody was last here, then comes to rest. */
const AWAKE_MS = 20_000, DROWSE_MS = 2600;
/** Milliseconds between pictures of what only drifts. */
const DRIFT_MS = 33;
/** The canvas is taken down this long after the page was left. */
const KEEP_MS = 45_000;
const DPR_MAX = 2;
/** Drawn smaller after so many frames slower than this, step by step down to this part of its size. */
const SLOW_MS = 26, SLOW_FRAMES = 40, STEP = 0.2, COARSE = 0.5;

interface Set { art: StageArt; focus: WebGLTexture[]; depth: WebGLTexture }
const REST: StageState = { focus: 0.6, veil: 0.6, play: 1, dolly: 0, lamps: 1, dev: 1, leak: 1, wide: 0 };

let current: Promise<Stage | null> | null = null;
let takenDown = 0;
const lostHandlers = new Set<() => void>();
/** The stage; null where there is no WebGL 2. */
export function photoStage(): Promise<Stage | null> {
  clearTimeout(takenDown);
  current ??= make();
  return current;
}
/** Calls [fn] after the canvas was lost: what stood on it starts over. Returns the way to stop listening. */
export function onStageLost(fn: () => void): () => void {
  lostHandlers.add(fn);
  return () => lostHandlers.delete(fn);
}

async function make(): Promise<Stage | null> {
  const canvas = document.createElement("canvas");
  canvas.className = "stage-gl";
  Object.assign(canvas.style, { position: "absolute", inset: "0", width: "100%", height: "100%", display: "block" });
  let gl: GL | null = null;
  try {
    gl = canvas.getContext("webgl2", { alpha: false, antialias: false, depth: false, stencil: false });
    if (!gl) return null;
    const prog = startProgram(gl, STAGE_VS, STAGE_FS);
    await prog.ready;
    return build(canvas, gl, prog);
  } catch {
    return null;
  }
}

function build(canvas: HTMLCanvasElement, gl: GL, prog: ReturnType<typeof startProgram>): Stage {
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  const quad = grid(gl, 1, 1);
  const time = createTimeline();
  let dead = false;
  const sets = new Map<string, Set>();
  const asked = new Map<string, Promise<boolean>>();

  /* ---------------------------------------------------------------- the pictures */
  async function fetchAll(art: StageArt): Promise<Set | null> {
    const pictures = await Promise.all([...art.focus, art.depth].map((url) => picture(url)));
    const made: WebGLTexture[] = [];
    for (const p of pictures) {
      // One at a time, with room for a frame between two.
      await new Promise<void>((done) => setTimeout(done, 0));
      if (dead) return null;
      made.push(texture(gl, p as Picture, { mips: made.length === 0 }));
      if ("close" in p) p.close();
    }
    const depth = made.pop()!;
    return { art, focus: made, depth };
  }
  function load(art: StageArt): Promise<boolean> {
    let p = asked.get(art.id);
    if (!p) {
      p = fetchAll(art).then((set) => {
        if (set) sets.set(art.id, set);
        return !!set;
      }, () => {
        asked.delete(art.id);
        return false;
      });
      asked.set(art.id, p);
    }
    return p;
  }

  /* ---------------------------------------------------------------- what is shown */
  let host: HTMLElement | null = null;
  let observer: ResizeObserver | null = null;
  let on = false;
  let size = { w: 0, h: 0 };
  let place: StageLayout = { side: 0, paper: [1, 1, 1], foot: null, title: null };
  let shown: Set | null = null;
  /** The one before, on its way out. */
  let gone: Set | null = null;
  const over = { k: 1 };
  const now: StageState = { ...REST };
  const lamp = { r1: 1, g1: 1, b1: 1, r2: 1, g2: 1, b2: 1, r3: 1, g3: 1, b3: 1, tinted: 0 };
  let turns: 1 | 2 | 3 = 3;
  let up = () => {};
  const isUp = new Promise<void>((done) => { up = done; });

  let target: Vec2 | null = null;
  const at = { x: 0, y: 0 };
  let woken = 0;
  let settled = false;
  const life = () => clamp(1 - (time.clock - woken - AWAKE_MS) / DROWSE_MS);

  function own(look: StageLook): void {
    const [r, g, b] = look.light;
    for (const k of [1, 2, 3] as const) Object.assign(lamp, { [`r${k}`]: r, [`g${k}`]: g, [`b${k}`]: b });
  }

  /* ---------------------------------------------------------------- each frame */
  let raf = 0;
  let last = 0;
  let dirty = false;
  /** Milliseconds since the last picture. */
  let since = 0;
  function run(): void {
    if (raf || !on || dead || !host) return;
    last = 0;
    raf = requestAnimationFrame(frame);
  }
  function wake(): void {
    dirty = true;
    run();
  }
  function frame(t: number): void {
    raf = 0;
    if (!on || dead || !host) return;
    const gap = last ? t - last : 16, dt = Math.min(64, gap);
    last = t;
    since += dt;
    const lively = time.busy || dirty || !settled;
    if (lively) pace(gap);
    if (lively || since >= DRIFT_MS - 2) {
      update(since);
      since = 0;
      dirty = false;
      draw();
    }
    if (time.busy || dirty || !settled || life() > 0) raf = requestAnimationFrame(frame);
  }
  let gaps: number[] = [];
  /** How large it is drawn; how long frames took before that was last made less; nothing more is to be tried. */
  let fine = 1, before = 0, capped = false;
  function pace(gap: number): void {
    if (capped || gap > 120) return;
    gaps.push(gap);
    if (gaps.length < SLOW_FRAMES) return;
    const mean = gaps.reduce((sum, v) => sum + v, 0) / gaps.length;
    gaps = [];
    // Where that did not help, something else keeps the frames apart (a battery saver).
    if (before && mean > before * 0.92) {
      fine += STEP;
      capped = true;
      return;
    }
    before = 0;
    if (mean < SLOW_MS || fine - STEP < COARSE) return;
    before = mean;
    fine -= STEP;
  }
  function update(dt: number): void {
    time.advance(dt);
    const t = time.clock / 1000, sway = life();
    const tx = target ? target[0] : 0.34 * Math.sin(t / 5.1) * sway;
    const ty = target ? target[1] : 0.24 * Math.sin(t / 6.7 + 1) * sway;
    const k = 1 - Math.exp(-dt / 170), dx = tx - at.x, dy = ty - at.y;
    at.x += dx * k;
    at.y += dy * k;
    settled = Math.abs(dx) + Math.abs(dy) < (target ? 0.002 : 0.02);
  }

  /** From here down it is paper behind the page. */
  const lowOf = () => (place.foot ? place.foot.y - LOW * place.foot.css : size.h * LOW_AT);
  /** The key visual's place, beside the sidebar or over the whole panel or on the way. */
  function frameOf(): Vec4 {
    const { w, h } = size, { side } = place, page = w - side;
    const near = Math.max(page * SPAN.page, (lowOf() / FLOOR_AT) * 16 / 9), far = Math.max(w * SPAN.whole, h * 0.8);
    const wide = lerp(near, far, now.wide);
    return [lerp(side + page / 2 - near * MIDDLE.page, w / 2 - far * MIDDLE.whole, now.wide), 0, wide, (wide * 9) / 16];
  }
  /** How bright each lamp is while they take turns. */
  function weights(): Vec3 {
    if (turns === 3) return [1, 1, 1];
    const beat = (time.clock / 1000 / 1.5) % 3;
    return [0, 1, 2].map((k) => {
      // One after the other, each coming up as the last goes down; by twos, each is down in turn.
      const d = Math.abs(((beat - k + 4.5) % 3) - 1.5), one = 1 - smooth(0.35, 0.85, d);
      return turns === 1 ? 0.16 + 1.14 * one : 1.16 - 0.96 * one;
    }) as unknown as Vec3;
  }
  function draw(): void {
    const set = shown;
    if (!set || !size.w) return;
    const dpr = (now.focus > SOFT ? 1 : Math.min(DPR_MAX, window.devicePixelRatio || 1)) * fine;
    const pw = Math.round(size.w * dpr), ph = Math.round(size.h * dpr);
    if (canvas.width !== pw) canvas.width = pw;
    if (canvas.height !== ph) canvas.height = ph;
    gl.viewport(0, 0, pw, ph);
    gl.disable(gl.BLEND);
    const kv = frameOf(), floor = kv[3] * FLOOR_AT, low = lowOf(), { look } = set.art, t = time.clock / 1000;
    const steps = set.focus.length - 1, f = clamp(now.focus) * steps, i = Math.min(steps - 1, Math.floor(f));
    prog.use();
    prog.tex("u_a", 0, set.focus[i]);
    prog.tex("u_b", 1, set.focus[i + 1]);
    prog.tex("u_far", 2, set.focus[steps]);
    prog.tex("u_depth", 3, set.depth);
    prog.tex("u_gone", 4, (gone ?? set).focus[steps]);
    const w = weights();
    const lamps = ([1, 2, 3] as const).map((k): Vec3 => {
      const v = w[k - 1] * (0.5 + 0.4 * lamp.tinted) * now.lamps;
      return [lamp[`r${k}`] * v, lamp[`g${k}`] * v, lamp[`b${k}`] * v];
    });
    const foot = place.foot ?? { x: kv[0] + kv[2] * 0.36, y: low, css: 1 };
    // Each lamp leans to and fro about where it is aimed.
    const aims: Vec2[] = [[foot.x - 92 * foot.css, low], [foot.x + 112 * foot.css, low], [foot.x + 8 * foot.css, foot.y]];
    const beams = look.lamps.slice(0, 3).map((l, k): Vec4 => {
      const x = kv[0] + l[0] * kv[2] - at.x * PLAY[0] * kv[2] * 0.4, y = kv[1] + l[1] * kv[3];
      const dx = aims[k][0] - x, dy = aims[k][1] - y;
      return [x, y, Math.atan2(dx, dy) + 0.075 * Math.sin(t / (2.9 + k * 0.7) + k * 2.1), Math.hypot(dx, dy)];
    });
    const play = now.play;
    const { title } = place;
    prog.set({
      u_res: [pw, ph], u_px: dpr, u_mix: f - i, u_kv: kv, u_floor: floor, u_side: place.side, u_low: low,
      u_par: [at.x * PLAY[0] * play, at.y * PLAY[1] * play], u_dolly: now.dolly,
      u_veil: now.veil, u_soft: clamp(now.focus), u_dev: now.dev, u_leak: now.leak, u_time: t,
      u_paper: place.paper, u_mist: look.mist, u_dark: look.dark, u_top: look.ground[0], u_bottom: look.ground[1],
      u_c1: lamps[0], u_c2: lamps[1], u_c3: lamps[2],
      u_b1: beams[0] ?? [0, -999, 0, 1], u_b2: beams[1] ?? [0, -999, 0, 1], u_b3: beams[2] ?? [0, -999, 0, 1],
      u_star: look.lamps[2] ?? [-1, -1],
      u_title: title ? [title.x + title.w / 2, title.y + title.h / 2, title.w, title.h] : [0, 0, 0, 0],
      u_over: over.k,
    });
    quad.draw();
    up();
  }

  function measure(): void {
    if (!host) return;
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h || w === size.w && h === size.h) return;
    size = { w, h };
    if (on && shown) draw();
    wake();
  }

  function takeDown(): void {
    if (dead) return;
    dead = true;
    cancelAnimationFrame(raf);
    observer?.disconnect();
    canvas.remove();
    gl.getExtension("WEBGL_lose_context")?.loseContext();
  }
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    const mine = !dead;
    current = null;
    takeDown();
    if (mine) for (const told of [...lostHandlers]) told();
  });

  return {
    up: isUp,
    load,
    mount(el) {
      if (dead) return;
      clearTimeout(takenDown);
      host = el;
      size = { w: 0, h: 0 };
      el.append(canvas);
      observer?.disconnect();
      observer = new ResizeObserver(measure);
      observer.observe(el);
      woken = time.clock;
      measure();
    },
    release() {
      cancelAnimationFrame(raf);
      raf = 0;
      observer?.disconnect();
      canvas.remove();
      host = null;
      target = null;
      clearTimeout(takenDown);
      takenDown = window.setTimeout(() => {
        current = null;
        takeDown();
      }, KEEP_MS);
    },
    show(art) {
      const next = sets.get(art.id);
      if (!next || next === shown) return;
      gone = shown;
      shown = next;
      if (!lamp.tinted) own(art.look);
      if (gone) {
        over.k = 0;
        void time.tween(over, { k: 1 }, 900, E.flow).then(() => { gone = null; });
      }
      wake();
    },
    seen(yes) {
      if (on === yes) return;
      on = yes;
      if (yes) {
        woken = time.clock;
        wake();
      } else {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    },
    layout(to) {
      place = to;
      wake();
    },
    pointer(to) {
      target = to;
      woken = time.clock;
      settled = false;
      run();
    },
    set(state) {
      for (const k in state) void time.tween(now, { [k]: state[k as keyof StageState] } as Numbers<StageState>, 1, E.linear);
      Object.assign(now, state);
      wake();
    },
    to(state, ms, ease = E.flow, delay = 0) {
      const done = time.tween(now, state as Numbers<StageState>, ms, ease, delay);
      wake();
      return done;
    },
    light(to) {
      woken = time.clock;
      const look = shown?.art.look;
      if (!look) return;
      turns = to?.turns ?? 3;
      const c = to ? [0, 1, 2].map((k) => to.tones[k % to.tones.length]) : [look.light, look.light, look.light];
      const colours = Object.fromEntries(c.flatMap((v, k) => [[`r${k + 1}`, v[0]], [`g${k + 1}`, v[1]], [`b${k + 1}`, v[2]]]));
      void time.tween(lamp, { ...colours, tinted: to ? 1 : 0 } as Numbers<typeof lamp>, to ? 520 : 760, E.flow);
      wake();
    },
  };
}
