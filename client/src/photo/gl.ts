// A thin layer over WebGL 2: programs, grids, textures and the few matrices the scene needs.
// The world is in design units: x right, y down, z toward the viewer, the origin in the middle of the stage.
import { RAD } from "./math";

export const DIST = 1500;

export type GL = WebGL2RenderingContext;
export type Vec2 = readonly [number, number];
export type Vec3 = readonly [number, number, number];
export type Vec4 = readonly [number, number, number, number];
/** Column by column. */
export type Mat4 = Float32Array<ArrayBuffer>;
export type Uniforms = Record<string, number | Vec2 | Vec3 | Vec4 | Mat4>;

export function context(canvas: HTMLCanvasElement, { alpha = false } = {}): GL {
  const gl = canvas.getContext("webgl2", { antialias: true, alpha });
  if (!gl) throw new Error("no webgl2");
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  return gl;
}

/** Attribute names, by their location in every program. */
const ATTRIBUTES = ["a", "b", "c"];
/** Between two looks at whether the driver is done. */
const POLL_MS = 8;

export interface Program {
  /** Linked: it can be used without holding the thread up. Rejects with the driver's log. */
  readonly ready: Promise<void>;
  /** Holds the thread up until it is linked. Throws the driver's log. */
  finish(): void;
  use(): void;
  set(values: Uniforms): void;
  tex(name: string, unit: number, texture: WebGLTexture): void;
  dispose(): void;
}

/** Hands a program to the driver and asks nothing back yet, so several compile side by side. */
export function startProgram(gl: GL, vs: string, fs: string): Program {
  const parallel = gl.getExtension("KHR_parallel_shader_compile");
  const compile = (type: number, src: string) => {
    const s = gl.createShader(type)!;
    gl.shaderSource(s, `#version 300 es\nprecision highp float;\n${src}`);
    gl.compileShader(s);
    return s;
  };
  const prog = gl.createProgram()!;
  const shaders = [compile(gl.VERTEX_SHADER, vs), compile(gl.FRAGMENT_SHADER, fs)];
  for (const s of shaders) gl.attachShader(prog, s);
  ATTRIBUTES.forEach((name, i) => gl.bindAttribLocation(prog, i, name));
  gl.linkProgram(prog);

  let linked = false;
  const finish = () => {
    if (linked) return;
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      const logs = [...shaders.map((s) => gl.getShaderInfoLog(s)), gl.getProgramInfoLog(prog)];
      throw new Error(logs.filter(Boolean).join("\n") || (gl.isContextLost() ? "context lost" : "program not linked"));
    }
    linked = true;
    for (const s of shaders) gl.deleteShader(s);
  };
  const settle = async () => {
    // Without the extension the first question waits for the driver: at least every program has been handed to it.
    if (!parallel) await pause(0);
    else while (!gl.getProgramParameter(prog, parallel.COMPLETION_STATUS_KHR)) await pause(POLL_MS);
    finish();
  };
  const locs = new Map<string, WebGLUniformLocation | null>();
  const loc = (n: string) => {
    let l = locs.get(n);
    if (l === undefined) locs.set(n, l = gl.getUniformLocation(prog, n));
    return l;
  };
  return {
    ready: settle(),
    finish,
    use() {
      finish();
      gl.useProgram(prog);
    },
    set(values) {
      for (const n in values) {
        const v = values[n], l = loc(n);
        if (l === null) continue;
        if (typeof v === "number") gl.uniform1f(l, v);
        else if (v instanceof Float32Array) gl.uniformMatrix4fv(l, false, v);
        else if (v.length === 2) gl.uniform2f(l, v[0], v[1]);
        else if (v.length === 3) gl.uniform3f(l, v[0], v[1], v[2]);
        else gl.uniform4f(l, v[0], v[1], v[2], v[3]);
      }
    },
    tex(n, unit, texture) {
      gl.activeTexture(gl.TEXTURE0 + unit);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      const l = loc(n);
      if (l !== null) gl.uniform1i(l, unit);
    },
    dispose: () => gl.deleteProgram(prog),
  };
}
const pause = (ms: number) => new Promise<void>((done) => setTimeout(done, ms));

export interface Mesh { draw(): void; dispose(): void }

/** A grid over 0..1 by 0..1. Its triangles face the viewer. */
export function grid(gl: GL, nx: number, ny: number): Mesh {
  const at = new Float32Array((nx + 1) * (ny + 1) * 2);
  for (let j = 0, k = 0; j <= ny; j++) for (let i = 0; i <= nx; i++) { at[k++] = i / nx; at[k++] = j / ny; }
  const ix = new Uint16Array(nx * ny * 6);
  for (let j = 0, k = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const p = j * (nx + 1) + i, q = p + nx + 1;
      ix.set([p, q, p + 1, p + 1, q, q + 1], k);
      k += 6;
    }
  }
  const vao = gl.createVertexArray(), points = gl.createBuffer(), order = gl.createBuffer();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, points);
  gl.bufferData(gl.ARRAY_BUFFER, at, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, order);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, ix, gl.STATIC_DRAW);
  gl.bindVertexArray(null);
  return {
    draw() {
      gl.bindVertexArray(vao);
      gl.drawElements(gl.TRIANGLES, ix.length, gl.UNSIGNED_SHORT, 0);
    },
    dispose() {
      gl.deleteVertexArray(vao);
      gl.deleteBuffer(points);
      gl.deleteBuffer(order);
    },
  };
}

export type Picture = HTMLImageElement | ImageBitmap;

export function image(url: string): Promise<HTMLImageElement> {
  return new Promise((ok, bad) => {
    const img = new Image();
    img.onload = () => img.decode().then(() => ok(img), () => ok(img));
    img.onerror = () => bad(new Error(url));
    img.src = url;
  });
}

/** A picture to make a texture of, its texels as they are in the file. A bitmap goes over several times faster than an
 *  image element, which holds the thread up for a frame. */
export async function picture(url: string): Promise<Picture> {
  try {
    const answer = await fetch(url);
    if (answer.ok) return await createImageBitmap(await answer.blob(), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
  } catch { /* an older browser, or a file it cannot fetch */ }
  return image(url);
}

/** [single]: only the first channel is kept. [srgb]: its colours are sRGB and are read as light, so that what is read
 *  between texels is mixed as light mixes. */
export function texture(gl: GL, source: TexImageSource | null,
  { mips = true, repeat = false, single = false, srgb = false } = {}): WebGLTexture {
  const t = gl.createTexture()!;
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, t);
  const wrap = repeat ? gl.REPEAT : gl.CLAMP_TO_EDGE;
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrap);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mips ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
  if (source) {
    if (single) gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, gl.RED, gl.UNSIGNED_BYTE, source);
    else gl.texImage2D(gl.TEXTURE_2D, 0, srgb ? gl.SRGB8_ALPHA8 : gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    if (mips) gl.generateMipmap(gl.TEXTURE_2D);
    const aniso = gl.getExtension("EXT_texture_filter_anisotropic");
    if (aniso && mips) gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, 4);
  }
  return t;
}

/** World to clip for a stage [w] by [h] design units wide at z = 0, seen from DIST in front of it. */
export function camera(w: number, h: number, shakeX = 0, shakeY = 0): Mat4 {
  const near = 200, far = 3400;
  const a = (far + near) / (near - far), b = (2 * far * near) / (near - far);
  const sx = (2 / w) * DIST, sy = (-2 / h) * DIST;
  // z' = z - DIST; w = -z'
  return new Float32Array([sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, a, -1, sx * shakeX, sy * shakeY, -DIST * a + b, DIST]);
}

/** The same eye, looking at a point [x], [y] design units off the middle of the view: what is drawn around the origin is
 *  drawn there, and seen from straight in front. */
export function lens(w: number, h: number, x: number, y: number): Mat4 {
  const m = camera(w, h);
  m[8] = (-2 / w) * x;
  m[12] = (2 / w) * x * DIST;
  m[9] = (2 / h) * y;
  m[13] = (-2 / h) * y * DIST;
  return m;
}

export const ident = (): Mat4 => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
export function mul(a: Mat4, b: Mat4): Mat4 {
  const o = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    const [x, y, z, w] = [b[c * 4], b[c * 4 + 1], b[c * 4 + 2], b[c * 4 + 3]];
    for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * x + a[4 + r] * y + a[8 + r] * z + a[12 + r] * w;
  }
  return o;
}
export const move = (x: number, y: number, z: number): Mat4 =>
  new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]);
export const scale = (x: number, y = x, z = x): Mat4 =>
  new Float32Array([x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0, 0, 0, 0, 1]);
export function rotX(r: number): Mat4 {
  const c = Math.cos(r), s = Math.sin(r);
  return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]);
}
export function rotY(r: number): Mat4 {
  const c = Math.cos(r), s = Math.sin(r);
  return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]);
}
export function rotZ(r: number): Mat4 {
  const c = Math.cos(r), s = Math.sin(r);
  return new Float32Array([c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
}

/** Where something is: in design units, angles in degrees, as CSS has them; `sx` and `sy` stretch it. */
export interface Pose {
  x: number; y: number; z: number;
  rx: number; ry: number; rz: number;
  s: number; sx?: number; sy?: number;
}
export const P = (x = 0, y = 0, o: Partial<Pose> = {}): Pose => ({ x, y, z: 0, rx: 0, ry: 0, rz: 0, s: 1, ...o });

/** Move, then lean. */
export function pose(p: Pose): Mat4 {
  let m = move(p.x, p.y, p.z);
  if (p.rz) m = mul(m, rotZ(p.rz * RAD));
  if (p.ry) m = mul(m, rotY(p.ry * RAD));
  if (p.rx) m = mul(m, rotX(p.rx * RAD));
  if (p.s !== 1 || p.sy) m = mul(m, scale(p.s * (p.sx ?? 1), p.s * (p.sy ?? 1), p.s));
  return m;
}
