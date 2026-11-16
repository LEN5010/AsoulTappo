// WebGL for the holo shading. Contexts are few and slow to make, so canvases are pooled: a view takes one while it
// shows a holo card and hands it back after, and the textures it last drew stay on it for the next time.
import type { HoloShine } from "../manifest";
import { FRAG, lightOf, shineUniforms, VERT, type Tilt } from "./shader";

const UNIFORMS = ["u_art", "u_mask", "u_light", "u_res", "u_on", "u_intensity", "u_skin", "u_cloth", "u_hueStart", "u_hueRange"] as const;
type Uniform = (typeof UNIFORMS)[number];

export interface HoloFrame {
  shine: HoloShine;
  tilt: Tilt;
  /** 1 under the pointer, a little less at rest. */
  on: number;
}

export class HoloRenderer {
  readonly canvas: HTMLCanvasElement;
  private gl: WebGLRenderingContext;
  private u = {} as Record<Uniform, WebGLUniformLocation | null>;
  private tex: [WebGLTexture, WebGLTexture];
  /** What the textures hold, so the same card is not uploaded twice. */
  private loaded: [string, string] = ["", ""];
  /** Size of the art, for the detail filter's step. */
  private artSize: [number, number] = [1, 1];
  lost = false;

  /** Throws when the context or the program cannot be made. */
  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "holo-canvas";
    const gl = this.canvas.getContext("webgl", { antialias: false, alpha: false, premultipliedAlpha: false });
    if (!gl) throw new Error("no webgl");
    this.gl = gl;
    const shader = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader");
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? "program");
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    for (const n of UNIFORMS) this.u[n] = gl.getUniformLocation(prog, n);
    gl.uniform1i(this.u.u_art, 0);
    gl.uniform1i(this.u.u_mask, 1);
    this.tex = [gl.createTexture()!, gl.createTexture()!];
    for (const t of this.tex) {
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }
    this.canvas.addEventListener("webglcontextlost", () => (this.lost = true));
  }

  /** Puts the art and the mask on the card. Throws when an image cannot be read (a cross-origin one without CORS). */
  setImages(artKey: string, art: HTMLImageElement, maskKey: string, mask: HTMLImageElement): void {
    const gl = this.gl;
    const upload = (n: 0 | 1, key: string, img: HTMLImageElement) => {
      if (this.loaded[n] === key) return;
      this.loaded[n] = "";
      gl.activeTexture(n ? gl.TEXTURE1 : gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.tex[n]);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
      this.loaded[n] = key;
    };
    upload(0, artKey, art);
    upload(1, maskKey, mask);
    this.artSize = [art.naturalWidth || 1, art.naturalHeight || 1];
  }

  /** Canvas pixels for a box of `width` CSS pixels at `ratio` (height / width). */
  resize(width: number, ratio: number): void {
    // A large card is drawn above screen resolution, as the browser resamples it when tilted. A small one stays at
    // screen resolution: shrunk while tilted, the canvas breaks up into blocks. Capped at the art's own width.
    const over = width >= 200 ? 1.5 : 1;
    const w = Math.max(1, Math.round(Math.min(this.artSize[0], width * (window.devicePixelRatio || 1) * over)));
    const h = Math.max(1, Math.round(w * ratio));
    if (this.canvas.width !== w) this.canvas.width = w;
    if (this.canvas.height !== h) this.canvas.height = h;
  }

  draw({ shine, tilt, on }: HoloFrame): void {
    if (this.lost) return;
    const gl = this.gl;
    const light = lightOf(tilt);
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.uniform2f(this.u.u_light, light.x, light.y);
    // The detail filter steps three texels of the art, as in the demo, whatever size the card is drawn at.
    gl.uniform2f(this.u.u_res, this.artSize[0], this.artSize[1]);
    gl.uniform1f(this.u.u_on, on);
    for (const [name, value] of Object.entries(shineUniforms(shine))) gl.uniform1f(this.u[name as Uniform], value);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  dispose(): void {
    this.gl.getExtension("WEBGL_lose_context")?.loseContext();
    this.lost = true;
  }
}

const spare: HoloRenderer[] = [];
/** Spare canvases kept for the next holo view; more than this are let go. */
const SPARE = 2;
let unsupported = false;

/** A canvas to draw on, or null where WebGL is not available. */
export function acquire(): HoloRenderer | null {
  if (unsupported) return null;
  for (let r = spare.pop(); r; r = spare.pop()) if (!r.lost) return r;
  try {
    return new HoloRenderer();
  } catch {
    unsupported = true;
    return null;
  }
}

export function release(r: HoloRenderer): void {
  r.canvas.remove();
  if (r.lost) return;
  if (spare.length < SPARE) spare.push(r);
  else r.dispose();
}

const images = new Map<string, Promise<HTMLImageElement>>();
const IMAGES = 24;

function fetchImage(url: string): Promise<HTMLImageElement> {
  return new Promise((ok, bad) => {
    const img = new Image();
    // Pack files come from the server; WebGL may only read them with CORS.
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => ok(img);
    img.onerror = () => bad(new Error(`image ${url}`));
    img.src = url;
  });
}

/**
 * An image WebGL may read. A copy cached from a plain <img> request carries no CORS header, so a failed load
 * is asked for once more under another URL.
 */
export function loadImage(url: string): Promise<HTMLImageElement> {
  const had = images.get(url);
  if (had) {
    images.delete(url);
    images.set(url, had);
    return had;
  }
  const retry = () => fetchImage(`${url}${url.includes("?") ? "&" : "?"}cors=1`);
  const p = fetchImage(url).catch(retry);
  p.catch(() => images.delete(url));
  images.set(url, p);
  while (images.size > IMAGES) images.delete(images.keys().next().value!);
  return p;
}

/** Fetches a holo card's images ahead of its showing. */
export function warmHolo(art: string, mask: string): void {
  if (art && mask) for (const url of [art, mask]) loadImage(url).catch(() => {});
}
