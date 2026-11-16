// The holo (镭射款) shading: the art with foil over the white of the official mask. Carried over from
// docs/assets/holo-demo/index.html (local notes), tuned there against the official recordings; keep the two in step.
import type { HoloShine } from "../manifest";

export const VERT = `
attribute vec2 a;
varying vec2 v_uv;
void main() {
  v_uv = vec2(a.x * 0.5 + 0.5, 0.5 - a.y * 0.5);
  gl_Position = vec4(a, 0.0, 1.0);
}`;

export const FRAG = `
precision highp float;
varying vec2 v_uv;
uniform sampler2D u_art;
uniform sampler2D u_mask;
uniform vec2 u_light;
uniform vec2 u_res;
uniform float u_on;
uniform float u_intensity;
uniform float u_skin;
uniform float u_cloth;
uniform float u_hueStart;
uniform float u_hueRange;

vec3 hsv2rgb(vec3 c) {
  vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
  vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
  return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}
vec3 rgb2hsv(vec3 c) {
  vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
  vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
  vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
  float d = q.x - min(q.w, q.y);
  float e = 1.0e-10;
  return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

void main() {
  vec3 base = texture2D(u_art, v_uv).rgb;
  float m = texture2D(u_mask, v_uv).r;

  vec3 hsv = rgb2hsv(base);
  float luma = dot(base, vec3(0.299, 0.587, 0.114));

  // Skin: warm hue, moderate saturation, bright.
  float dh = abs(fract(hsv.x - 0.06 + 0.5) - 0.5);
  float skin = (1.0 - smoothstep(0.035, 0.09, dh))
             * smoothstep(0.08, 0.18, hsv.y) * (1.0 - smoothstep(0.5, 0.7, hsv.y))
             * smoothstep(0.45, 0.72, hsv.z);
  float protect = pow(clamp(1.0 - skin, 0.0, 1.0), u_skin * 1.6);

  // Light fabric and paper: low saturation, bright.
  float cloth = (1.0 - smoothstep(0.12, 0.45, hsv.y)) * smoothstep(0.4, 0.85, hsv.z);

  // Official intensity runs 0.42 to 1.55; squeeze it so every card lands at a similar level.
  float level = mix(0.68, 0.92, clamp((u_intensity - 0.4) / 1.15, 0.0, 1.0));
  float w = m * level * protect * (1.0 + 0.08 * u_cloth * cloth) * mix(0.9, 1.0, u_on);
  // Very light areas (sky, white buildings) keep more of the print so the foil doesn't look painted on.
  w *= mix(1.0, 0.72, smoothstep(0.6, 0.95, luma));
  w = clamp(w, 0.0, 0.92);

  // Fine detail of the art (edges, windows, line work): luma minus a small blur.
  vec2 o = 3.0 / u_res;
  vec3 Y = vec3(0.299, 0.587, 0.114);
  float blur = (dot(texture2D(u_art, v_uv + vec2(o.x, 0.0)).rgb, Y)
              + dot(texture2D(u_art, v_uv - vec2(o.x, 0.0)).rgb, Y)
              + dot(texture2D(u_art, v_uv + vec2(0.0, o.y)).rgb, Y)
              + dot(texture2D(u_art, v_uv - vec2(0.0, o.y)).rgb, Y)
              + dot(texture2D(u_art, v_uv + o).rgb, Y)
              + dot(texture2D(u_art, v_uv - o).rgb, Y)
              + dot(texture2D(u_art, v_uv + vec2(o.x, -o.y)).rgb, Y)
              + dot(texture2D(u_art, v_uv + vec2(-o.x, o.y)).rgb, Y)) / 8.0;
  // Clamped so halftone dots don't clip at white and drag the foil darker.
  float detail = clamp(luma - blur, -0.07, 0.07);

  // Hue: runs from hue_start on the left to the far end of the band on the right and slides as the card tilts.
  vec2 lp = u_light - 0.5;
  float phase = 0.5 + v_uv.x * 0.6 + v_uv.y * 0.15 - dot(lp, vec2(1.1, 0.5));
  float tri = abs(fract(phase) * 2.0 - 1.0);
  float hue = fract(u_hueStart + tri * u_hueRange);

  // Brightness: a wide band of reflected light that sweeps across with the tilt, about 0.9 of a light/dark
  // cycle across the card, so part of the foil is lit at a time and never all of it.
  float band = 0.5 + 0.5 * cos((v_uv.x * 0.9 + v_uv.y * 0.35 - lp.x * 1.6 - lp.y * 0.8) * 3.1416 * 1.8);
  // Away from the light the printed art shows through again instead of a dark, muddy foil.
  float bright = smoothstep(0.5, 0.9, band);
  float value = mix(0.55, 1.0, bright);
  float sat = mix(0.55, 0.46, bright);
  // Foil keeps part of the art's light and shade plus its fine detail.
  vec3 foil = hsv2rgb(vec3(hue, sat, value)) * (0.94 + 0.1 * luma) + vec3(detail * 2.0);
  w *= mix(0.35, 1.0, bright);

  vec3 col = mix(base, foil, w);

  // Faint gloss over the whole card under the light.
  vec2 d = (v_uv - u_light) * vec2(1.0, 1.5);
  col += vec3(exp(-dot(d, d) * 5.0) * 0.05 * u_on);

  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

/** A card's lean in degrees: rx turns the top away (positive) or toward the viewer, ry turns the right side away. */
export interface Tilt { rx: number; ry: number }
export const FLAT: Tilt = { rx: 0, ry: 0 };

/** Largest lean the pointer gives a holo card, either way. */
export const MAX_TILT = 10;

/**
 * Where the light falls on the card (0 to 1 across, 0 to 1 down) for a lean: the demo's mapping, where the
 * pointer at the right edge turns the card 11 degrees and lights its right side.
 */
export function lightOf(tilt: Tilt): { x: number; y: number } {
  const clamp = (n: number) => Math.min(1, Math.max(0, n));
  return { x: clamp(0.5 + tilt.ry / 22), y: clamp(0.5 - tilt.rx / 22) };
}

/** The lean toward a point on the card (0 to 1 each way), at most `max` degrees either way. */
export function tiltToward(x: number, y: number, max = MAX_TILT): Tilt {
  const clamp = (n: number) => Math.min(1, Math.max(0, n));
  return { rx: (0.5 - clamp(y)) * 2 * max, ry: (clamp(x) - 0.5) * 2 * max };
}

/** CSS for a lean, about the element's centre. */
export function tiltTransform(tilt: Tilt, perspective = 900): string {
  return `perspective(${perspective}px) rotateX(${tilt.rx.toFixed(2)}deg) rotateY(${tilt.ry.toFixed(2)}deg)`;
}

/** Uniform values of a shine, by uniform name. */
export function shineUniforms(shine: HoloShine): Record<string, number> {
  return {
    u_intensity: shine.laserIntensity,
    u_skin: shine.skinProtection,
    u_cloth: shine.clothBoost,
    u_hueStart: shine.hueStart,
    u_hueRange: shine.hueRange,
  };
}
