// What every view of the photocards on one WebGL context shares: programs, meshes and textures, the signatures and the
// small pictures of a series, and the full-size textures of cards about to be drawn or drawn lately.
import { cardThumb, OPEN_ART, seriesArt, type CardInfo } from "./art";
import * as G from "./gl";
import type { GL, Program, Vec4 } from "./gl";
import * as SH from "./shaders";

const SOURCES = {
  foil: [SH.FOIL_VS, SH.FOIL_FS],
  card: [SH.CARD_VS, SH.CARD_FS],
  rim: [SH.CARD_VS, SH.RIM_FS],
  box: [SH.BOX_VS, SH.BOX_FS],
  shadow: [SH.FLAT_VS, SH.SHADOW_FS],
  thumb: [SH.FLAT_VS, SH.THUMB_FS],
  desk: [SH.FLAT_VS, SH.DESK_FS],
  rays: [SH.FLAT_VS, SH.RAYS_FS],
  slit: [SH.FLAT_VS, SH.SLIT_FS],
  beam: [SH.FLAT_VS, SH.BEAM_FS],
  wash: [SH.FLAT_VS, SH.WASH_FS],
  bits: [SH.BIT_VS, SH.BIT_FS],
  disc: [SH.FLAT_VS, SH.DISC_FS],
} as const;
export type ProgramName = keyof typeof SOURCES;

/** The side of the atlas of small pictures. */
const ATLAS = 2048;
/** Fronts nobody asked to keep that stay loaded. */
const SPARE = 4;
/** The short side of a front's smaller picture, in texels. */
const SMALL = 540;

export type CardSide = "front" | "behind";
/** A side of a card: nothing to draw until it is ready. `ready` resolves even when a picture could not be loaded. */
export interface SideTexture {
  readonly base: WebGLTexture | null;
  readonly mat: WebGLTexture | null;
  readonly ready: Promise<void>;
}
/** Both sides of a card, loaded. */
export interface Faces { base: WebGLTexture; mat: WebGLTexture; baseB: WebGLTexture; matB: WebGLTexture }
/** Small pictures of every card of a series, on one texture. */
export interface Thumbs {
  /** There once they are drawn. */
  texture: WebGLTexture;
  /** A card's place on it, 0 to 1: left, top, right, bottom. */
  rect(card: string): Vec4;
  /** They are on it, all at once; `ready` resolves then. */
  drawn: boolean;
  ready: Promise<void>;
}
/** Particles: one buffer of eight numbers each, filled for every picture. */
export interface Bits { draw(data: Float32Array<ArrayBuffer>, count: number): void; dispose(): void }

export interface Kit {
  readonly progs: Record<ProgramName, Program>;
  readonly mesh: Record<"quad" | "fine" | "low" | "strip" | "card" | "board" | "flap", G.Mesh>;
  readonly bits: Bits;
  /** There once `ready` resolves: the room foil mirrors, a soft shadow, random texels. */
  readonly tex: Record<"room" | "shadow" | "noise", WebGLTexture>;
  /** The programs and the shared textures can be used. Rejects when one of them cannot be made. */
  readonly ready: Promise<void>;
  /** Pictures asked for are still being loaded. */
  readonly busy: boolean;
  /** Loads what every card of a series needs, its signatures and its backs, the print of its box, and its floor. */
  load(series: string): Promise<void>;
  /** The print of a series' box alone, and its signatures alone. */
  ink(series: string): Promise<void>;
  signs(series: string): Promise<void>;
  /** The print of a series' box; null until it is loaded. */
  print(series: string): WebGLTexture | null;
  /** The key visual far out of focus, for the floor of its stage; null until it is loaded, and without one. */
  floor(series: string): WebGLTexture | null;
  /** The texture of a signed card's signature; null until its series is loaded. */
  sign(info: CardInfo): WebGLTexture | null;
  /** The small pictures of a series. The first call starts to draw them. */
  thumbs(series: string): Thumbs;
  /** A card's own textures, loaded ahead of its turn and let go a while after. */
  want(info: CardInfo, side: CardSide): SideTexture;
  /** A card's front at half its size, for a view that shows it small and never its back. */
  small(info: CardInfo): SideTexture;
  /** What to draw a card with; null until both its sides are loaded. */
  faces(info: CardInfo, small?: boolean): Faces | null;
  /** Lets go of fronts, but for those of [keep] and the few used last; of every back too with [backs]. */
  letGo(keep: readonly CardInfo[], spare?: number, backs?: boolean): void;
  /** The same for the smaller fronts. */
  letGoSmall(keep: readonly CardInfo[], spare?: number): void;
  /** The textures asked for so far are loaded. */
  settled(): Promise<void>;
  dispose(): void;
}

export function createKit(gl: GL): Kit {
  let disposed = false;
  const progs = Object.fromEntries(
    Object.entries(SOURCES).map(([name, [vs, fs]]) => [name, G.startProgram(gl, vs, fs)]),
  ) as Kit["progs"];
  const mesh: Kit["mesh"] = {
    quad: G.grid(gl, 1, 1), fine: G.grid(gl, 36, 52), low: G.grid(gl, 14, 18), strip: G.grid(gl, 72, 5),
    card: G.grid(gl, 44, 56), board: G.grid(gl, 20, 20), flap: G.grid(gl, 16, 32),
  };
  const bits = makeBits(gl);

  /** Loads under way. */
  let pending = 0;
  function track<T>(p: Promise<T>): Promise<T> {
    pending++;
    const done = () => { pending--; };
    p.then(done, done);
    return p;
  }

  let turns: Promise<unknown> = Promise.resolve();
  /** Textures are made one at a time, with room for a frame between two of them. Null once this is disposed of. */
  function upload(
    picture: G.Picture, make: (p: G.Picture) => WebGLTexture | null = (p) => G.texture(gl, p),
  ): Promise<WebGLTexture | null> {
    const mine = turns.then(() => new Promise<void>((done) => setTimeout(done, 0))).then(() => {
      const made = disposed ? null : make(picture);
      if ("close" in picture) picture.close();
      return made;
    });
    turns = mine.catch(() => {});
    return mine;
  }

  const tex = {} as Kit["tex"];
  const shared = track(Promise.all([OPEN_ART.room, OPEN_ART.shadow].map((url) => G.picture(url).then((p) => upload(p))))).then(([room, shadow]) => {
    if (disposed || !room || !shadow) return;
    Object.assign(tex, { room, shadow });
    // The same random texels as the card page's grain.
    const noise = new Uint8Array(256 * 256 * 4);
    let s = 20261123;
    for (let i = 0; i < noise.length; i++) { s = (s * 1664525 + 1013904223) >>> 0; noise[i] = s >>> 24; }
    tex.noise = G.texture(gl, null, { mips: false, repeat: true });
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 256, 0, gl.RGBA, gl.UNSIGNED_BYTE, noise);
  });

  /* ---------------------------------------------------------------- a series */
  const signs = new Map<string, WebGLTexture>();
  const prints = new Map<string, WebGLTexture>();
  const floors = new Map<string, WebGLTexture>();
  /** What was asked for once, by what and whose it is; what did not all come is asked for anew. */
  const asked = new Map<string, Promise<void>>();
  function once(key: string, begin: () => Promise<boolean>): Promise<void> {
    let p = asked.get(key);
    if (!p) asked.set(key, p = track(begin()).catch(() => false).then((whole) => { if (!whole) asked.delete(key); }));
    return p;
  }
  async function loadSigns(series: string): Promise<boolean> {
    const art = seriesArt(series);
    const there = await Promise.all(Object.values(art?.signs ?? {}).map(async (s) => {
      if (signs.has(`${series}/${s.member}`)) return true;
      const picture = await G.picture(s.url).catch(() => null);
      const made = picture && await upload(picture, (p) => {
        // Its channels are not colours.
        gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
        const t = G.texture(gl, p);
        gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.BROWSER_DEFAULT_WEBGL);
        return t;
      });
      if (made) signs.set(`${series}/${s.member}`, made);
      return !!made;
    }));
    return there.every(Boolean);
  }
  async function loadInk(series: string): Promise<boolean> {
    const art = seriesArt(series), picture = art && await G.picture(art.boxInk).catch(() => null);
    const made = picture && await upload(picture, (p) => G.texture(gl, p, { single: true }));
    if (made) prints.set(series, made);
    return !!made;
  }
  async function loadBacks(series: string): Promise<void> {
    const backs = new Map((seriesArt(series)?.cards ?? []).map((c) => [c.back, c]));
    await Promise.all([...backs.values()].map((c) => want(c, "behind").ready));
  }
  async function loadFloor(series: string): Promise<boolean> {
    const url = seriesArt(series)?.stage?.focus.at(-1);
    if (!url) return true;
    const picture = await G.picture(url).catch(() => null);
    const made = picture && await upload(picture);
    if (made) floors.set(series, made);
    return !!made;
  }
  const inkOf = (series: string) => once(`ink/${series}`, () => loadInk(series));
  const floorOf = (series: string) => once(`floor/${series}`, () => loadFloor(series));
  const signsOf = (series: string) => once(`signs/${series}`, () => loadSigns(series));

  const sheets = new Map<string, Thumbs>();
  /** Room for 16 cards that stand and 12 that lie on their side. */
  function makeThumbs(series: string): Thumbs {
    const cards = seriesArt(series)?.cards ?? [];
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = ATLAS;
    const pen = canvas.getContext("2d")!;
    const cells = new Map<string, Vec4>(), rects = new Map<string, Vec4>();
    let p = 0, l = 0;
    for (const c of cards) {
      const w = c.land ? 500 : 250, h = c.land ? 314 : 398;
      const n = c.land ? l++ : p++;
      const x = c.land ? (n % 4) * 512 + 4 : (n % 8) * 256 + 3;
      const y = c.land ? 840 + Math.floor(n / 4) * 326 : Math.floor(n / 8) * 410 + 4;
      cells.set(c.id, [x, y, w, h]);
      rects.set(c.id, [x / ATLAS, y / ATLAS, (x + w) / ATLAS, (y + h) / ATLAS]);
    }
    const made = { rect: (card) => rects.get(card)!, drawn: false, ready: Promise.resolve() } as Thumbs;
    const fill = async () => {
      const small = await Promise.all(cards.map((c) => G.image(cardThumb(c) ?? c.front[0]).catch(() => null)));
      if (disposed) return;
      pen.imageSmoothingQuality = "high";
      cards.forEach((c, i) => {
        const img = small[i];
        if (img) pen.drawImage(img, ...(cells.get(c.id)! as [number, number, number, number]));
      });
      made.texture = G.texture(gl, canvas);
      made.drawn = true;
    };
    made.ready = track(fill());
    return made;
  }

  /* ---------------------------------------------------------------- pictures of cards */
  /** A picture as a texture, shared by everything that needs it: cards of a template share their finishes. */
  interface Held { key: string; tex: WebGLTexture | null; users: number; ready: Promise<void> }
  const held = new Map<string, Held>();
  function hold(url: string, small: boolean): Held {
    const key = small ? `${url} small` : url;
    let h = held.get(key);
    if (!h) {
      const made: Held = { key, tex: null, users: 0, ready: Promise.resolve() };
      held.set(key, h = made);
      made.ready = track(G.picture(url).then((picture) => upload(picture, (p) => (
        made.users ? G.texture(gl, small ? shrunk(p) : p) : null))).then((tex) => {
        if (!tex) return;
        if (made.users && !disposed) made.tex = tex;
        else gl.deleteTexture(tex);
      }));
    }
    h.users += 1;
    return h;
  }
  function drop(h: Held): void {
    h.users -= 1;
    if (h.users > 0) return;
    if (h.tex) gl.deleteTexture(h.tex);
    held.delete(h.key);
  }
  function shrunk(p: G.Picture): HTMLCanvasElement {
    const [w, h] = "naturalWidth" in p ? [p.naturalWidth, p.naturalHeight] : [p.width, p.height];
    const k = SMALL / Math.min(w, h), c = document.createElement("canvas");
    c.width = Math.round(w * k);
    c.height = Math.round(h * k);
    const pen = c.getContext("2d")!;
    pen.imageSmoothingQuality = "high";
    pen.drawImage(p, 0, 0, c.width, c.height);
    return c;
  }

  type Size = CardSide | "small";
  class Full implements SideTexture {
    used = 0;
    ready: Promise<void>;
    private readonly parts: [Held, Held];
    constructor(readonly size: Size, info: CardInfo, failed: () => void) {
      const [base, mat] = info[size === "behind" ? "behind" : "front"];
      this.parts = [hold(base, size === "small"), hold(mat, size === "small")];
      this.ready = Promise.all(this.parts.map((h) => h.ready)).then(() => {}, failed);
    }
    get base() { return this.parts[0].tex; }
    get mat() { return this.parts[1].tex; }
    drop() { this.parts.forEach(drop); }
  }
  const full = new Map<string, Full>();
  /** Counts uses, to tell which was the last. */
  let uses = 0;
  /** A signed card has the sides of its solo card; several cards share a back. */
  const nameOf = (info: CardInfo, size: Size) => `${info.series}/${size === "behind" ? info.back : info.id}-${size}`;

  function want(info: CardInfo, size: Size): SideTexture {
    const name = nameOf(info, size);
    let f = full.get(name);
    if (!f) {
      const made = new Full(size, info, () => forget(name, made));
      full.set(name, f = made);
    }
    f.used = ++uses;
    return f;
  }
  function forget(name: string, f: Full): void {
    if (full.get(name) !== f) return;
    full.delete(name);
    f.drop();
  }
  /** Lets go of what is there of a size, but for what is kept and the few used last. */
  function thin(size: Size, keep: readonly CardInfo[], spare: number): void {
    const kept = new Set(keep.map((c) => nameOf(c, size)));
    const loose = [...full].filter(([n, f]) => f.size === size && f.base && !kept.has(n)).sort((a, b) => a[1].used - b[1].used);
    for (const [n, f] of loose.slice(0, Math.max(0, loose.length - spare))) forget(n, f);
  }

  return {
    progs, mesh, bits, tex,
    ready: Promise.all([shared, ...Object.values(progs).map((p) => p.ready)]).then(() => {}),
    get busy() { return pending > 0; },
    ink: inkOf,
    signs: signsOf,
    async load(series) { await Promise.all([inkOf(series), signsOf(series), loadBacks(series), floorOf(series)]); },
    print: (series) => prints.get(series) ?? null,
    floor: (series) => floors.get(series) ?? null,
    sign: (info) => (info.signed && signs.get(`${info.series}/${info.signed.member}`)) ?? null,
    thumbs(series) {
      let t = sheets.get(series);
      if (!t) sheets.set(series, t = makeThumbs(series));
      return t;
    },
    want,
    small: (info) => want(info, "small"),
    faces(info, small = false) {
      const f = full.get(nameOf(info, small ? "small" : "front")), b = small ? f : full.get(nameOf(info, "behind"));
      if (!f?.base || !f.mat || !b?.base || !b.mat) return null;
      f.used = b.used = ++uses;
      return { base: f.base, mat: f.mat, baseB: b.base, matB: b.mat };
    },
    letGo(keep, spare = SPARE, backs = false) {
      thin("front", keep, spare);
      if (backs) thin("behind", keep, 0);
    },
    letGoSmall: (keep, spare = SPARE) => thin("small", keep, spare),
    async settled() { await Promise.all([...full.values()].map((f) => f.ready)); },
    dispose() {
      disposed = true;
      for (const p of Object.values(progs)) p.dispose();
      for (const m of Object.values(mesh)) m.dispose();
      bits.dispose();
      for (const t of [...Object.values(tex), ...signs.values(), ...prints.values(), ...floors.values()]) gl.deleteTexture(t);
      for (const t of sheets.values()) gl.deleteTexture(t.texture);
      for (const h of held.values()) if (h.tex) gl.deleteTexture(h.tex);
      signs.clear();
      prints.clear();
      floors.clear();
      sheets.clear();
      full.clear();
      held.clear();
    },
  };
}

function makeBits(gl: GL): Bits {
  const vao = gl.createVertexArray(), data = gl.createBuffer(), corners = gl.createBuffer();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, corners);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-0.5, -0.5, -0.5, 0.5, 0.5, -0.5, 0.5, 0.5]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, data);
  for (const [l, at] of [[1, 0], [2, 16]]) {
    gl.enableVertexAttribArray(l);
    gl.vertexAttribPointer(l, 4, gl.FLOAT, false, 32, at);
    gl.vertexAttribDivisor(l, 1);
  }
  gl.bindVertexArray(null);
  return {
    draw(list, count) {
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, data);
      gl.bufferData(gl.ARRAY_BUFFER, list, gl.DYNAMIC_DRAW);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, count);
      gl.bindVertexArray(null);
    },
    dispose() {
      gl.deleteVertexArray(vao);
      gl.deleteBuffer(data);
      gl.deleteBuffer(corners);
    },
  };
}
