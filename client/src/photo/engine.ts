// One WebGL 2 canvas for every view of the photocards. Its programs and textures are made once; the canvas element itself
// moves into the view on top (the shelf on the page, the table a box is opened on, a card looked at), and a view it leaves
// keeps a still picture of itself, unless what it showed goes along.
// Frames are drawn only while the view on top can be seen and something in it moves.
import { context } from "./gl";
import { createKit, type Kit } from "./kit";
import { createPainter, type Painter } from "./painter";

export interface PhotoGl {
  canvas: HTMLCanvasElement;
  gl: WebGL2RenderingContext;
  kit: Kit;
  painter: Painter;
}
export interface Scene {
  /** Its host's size in CSS pixels, and device pixels to one of them. */
  resize(w: number, h: number, dpr: number): void;
  update(dt: number): void;
  draw(): void;
  /** Something moves: another frame follows. */
  readonly busy: boolean;
}
export interface Mount {
  /** Draws, and goes on while the scene is busy. */
  wake(): void;
  /** Whether the view can be seen at all. */
  show(on: boolean): void;
  /** Another scene in the same place. */
  swap(scene: Scene): void;
  /** Gives the canvas back to the view under it. */
  release(): void;
}

/** The longest step of time a frame takes: a window that was away does not jump. */
const MAX_STEP_MS = 48;
const DPR_MAX = 2;
/** Frames slower than this on average, over as many, are drawn smaller. */
const SLOW_MS = 23;
const SLOW_FRAMES = 45;
const QUALITY_STEP = 0.2;
const QUALITY_MIN = 0.6;
/** Once they were quicker than this for so long, they are drawn at full size again. */
const QUICK_MS = 21;
const WELL_MS = 4000;

let current: Promise<PhotoGl | null> | null = null;
let engine: PhotoGl | null = null;
let quality = 1;
const lostHandlers = new Set<() => void>();

/** The shared canvas and what is drawn with; null where there is no WebGL 2. */
export function photoGl(): Promise<PhotoGl | null> {
  if (!current) {
    const asked = current = make();
    // One that could not be made is made anew when it is next asked for.
    void asked.then((made) => { if (!made && current === asked) current = null; });
  }
  return current;
}

async function make(): Promise<PhotoGl | null> {
  const canvas = document.createElement("canvas");
  canvas.className = "photo-gl";
  Object.assign(canvas.style, { position: "absolute", inset: "0", width: "100%", height: "100%", display: "block" });
  try {
    const gl = context(canvas, { alpha: true });
    const kit = createKit(gl);
    const made: PhotoGl = { canvas, gl, kit, painter: createPainter(gl, kit) };
    canvas.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      lose(made);
    });
    engine = made;
    followDensity();
    await kit.ready;
    return engine === made ? made : null;
  } catch {
    // The canvas may have been lost, and another made, since.
    if (engine?.canvas === canvas) engine = null;
    return null;
  }
}

let following = false;
/** Draws anew once the window has come to a screen of another density: its size in CSS pixels need not change then. */
function followDensity(): void {
  if (following || typeof matchMedia !== "function") return;
  following = true;
  const wait = () => matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`).addEventListener("change", () => {
    const e = top();
    if (e) fit(e);
    wait();
  }, { once: true });
  wait();
}

/** The context went away (a sleeping machine, a driver reset): everything is made anew, and the views start over. */
function lose(which: PhotoGl): void {
  if (engine !== which) return;
  engine = null;
  current = null;
  stop();
  for (const e of stack) {
    e.observer.disconnect();
    e.still?.remove();
  }
  stack.length = 0;
  which.canvas.remove();
  for (const told of [...lostHandlers]) told();
}
/** Calls [fn] after the canvas was lost: its views mount again. Returns the way to stop listening. */
export function onPhotoLost(fn: () => void): () => void {
  lostHandlers.add(fn);
  return () => lostHandlers.delete(fn);
}

interface Entry {
  host: HTMLElement;
  scene: Scene;
  layer: number;
  shown: boolean;
  still: HTMLCanvasElement | null;
  observer: ResizeObserver;
  size: { w: number; h: number };
}
const stack: Entry[] = [];
const top = () => stack[stack.length - 1];

let raf = 0;
let last = 0;
let dirty = false;
let slow: number[] = [];
/** How long frames took before they were last drawn smaller, until it is known whether that helped. */
let before = 0;
let capped = false;
/** How long they have been quick, and how long they have to be: longer each time, not to go back and forth. */
let well = 0;
let patience = WELL_MS;

function stop(): void {
  cancelAnimationFrame(raf);
  raf = 0;
}
function run(): void {
  if (raf || !top()?.shown) return;
  last = 0;
  raf = requestAnimationFrame(frame);
}
function frame(now: number): void {
  const mine = raf, e = top();
  if (!engine || !e?.shown) {
    raf = 0;
    return;
  }
  const gap = last ? now - last : 16;
  last = now;
  dirty = false;
  let again = false;
  try {
    e.scene.update(Math.min(MAX_STEP_MS, gap));
    e.scene.draw();
    if (e.scene.busy) pace(gap);
    again = e.scene.busy || dirty;
  } finally {
    // Woken meanwhile, it goes on from here; but not once it was stopped, or another view has begun its own frames.
    if (raf === mine) raf = again ? requestAnimationFrame(frame) : 0;
  }
}
/** Drawn smaller after a run of slow frames; a single long one (a page mounting) tells nothing. Where that does not help,
 *  something else keeps the frames apart (a battery saver): it goes back, and stays until they are quick again. */
function pace(gap: number): void {
  if (gap > 120) return;
  slow.push(gap);
  if (slow.length < SLOW_FRAMES) return;
  const mean = slow.reduce((sum, v) => sum + v, 0) / slow.length;
  slow = [];
  const size = quality;
  well = mean < QUICK_MS ? well + mean * SLOW_FRAMES : 0;
  if (before && mean > before * 0.92) {
    quality += QUALITY_STEP;
    capped = true;
  } else if (mean >= SLOW_MS && !capped) quality = Math.max(QUALITY_MIN, quality - QUALITY_STEP);
  else if (well >= patience && (quality < 1 || capped)) {
    quality = 1;
    capped = false;
    well = 0;
    patience *= 2;
  }
  before = size - quality > 0.01 ? mean : 0;
  const e = top();
  if (e && quality !== size) fit(e);
}

function fit(e: Entry): void {
  if (!engine || e !== top()) return;
  const w = e.host.clientWidth, h = e.host.clientHeight;
  if (!w || !h) return;
  const dpr = Math.min(DPR_MAX, window.devicePixelRatio || 1) * quality;
  const pw = Math.max(1, Math.round(w * dpr)), ph = Math.max(1, Math.round(h * dpr));
  const { canvas } = engine;
  if (canvas.width !== pw) canvas.width = pw;
  if (canvas.height !== ph) canvas.height = ph;
  e.size = { w, h };
  e.scene.resize(w, h, dpr);
  e.scene.draw();
  run();
}
function claim(e: Entry): void {
  if (!engine) return;
  stop();
  // Whether the last step helped is not known yet.
  if (before) quality = Math.min(1, quality + QUALITY_STEP);
  slow = [];
  before = 0;
  e.host.append(engine.canvas);
  fit(e);
  if (e.still) e.still.style.visibility = "hidden";
}
/** A picture of the view as it is, left in its place. */
function keepStill(e: Entry): void {
  if (!engine || !engine.canvas.width) return;
  if (!e.still) {
    e.still = document.createElement("canvas");
    Object.assign(e.still.style, { position: "absolute", inset: "0", width: "100%", height: "100%" });
    e.host.prepend(e.still);
  }
  e.still.width = engine.canvas.width;
  e.still.height = engine.canvas.height;
  e.scene.draw();
  e.still.getContext("2d")?.drawImage(engine.canvas, 0, 0);
  e.still.style.visibility = "";
}

/**
 * Shows [scene] in [host], over the views of its layer and those under it: 0 a page, 1 the table, 2 a card looked at. The
 * one it covers keeps a still picture, or with [bare] nothing: what it showed goes on in the new view.
 */
export function mountScene(host: HTMLElement, scene: Scene, { bare = false, layer = 0 } = {}): Mount {
  const under = top();
  const e: Entry = {
    host, scene, layer, shown: true, still: null, size: { w: 0, h: 0 },
    observer: new ResizeObserver(() => { if (host.clientWidth !== e.size.w || host.clientHeight !== e.size.h) fit(e); }),
  };
  let at = stack.length;
  while (at > 0 && stack[at - 1].layer > layer) at--;
  stack.splice(at, 0, e);
  e.observer.observe(host);
  // One that comes back under another (the canvas was lost meanwhile) waits for its turn.
  if (e === top()) {
    if (under && !bare) keepStill(under);
    else if (under?.still) under.still.style.visibility = "hidden";
    claim(e);
  }
  return {
    wake() {
      dirty = true;
      if (e === top()) run();
    },
    show(on) {
      if (e.shown === on) return;
      e.shown = on;
      if (e !== top()) return;
      if (on) {
        fit(e);
        dirty = true;
        run();
      } else stop();
    },
    swap(next) {
      e.scene = next;
      fit(e);
    },
    release() {
      const at = stack.indexOf(e);
      e.observer.disconnect();
      e.still?.remove();
      if (at < 0) return;
      const was = e === top();
      stack.splice(at, 1);
      if (!was) return;
      stop();
      engine?.canvas.remove();
      const back = top();
      if (back) claim(back);
    },
  };
}
