// Shaders of the opening scene. The card's finishes are the very ones of ../index.html, read from that page.

const COMMON = `
uniform mat4 u_vp;
uniform mat4 u_model;
`;

/* The light a bag holds: one colour for each member on the card, side by side along the mouth; one gold for a signature.
 * s runs from -1 at the bag's left side to 1 at its right. */
const LIGHT = `
uniform float u_n;         // how many colours
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_c3;
float lsq(float v) { return v * v; }
// Each in its own stretch, w the half-width of what lies between two of them.
vec3 lightBand(float s, float w) {
  if (u_n < 1.5) return u_c1;
  if (u_n < 2.5) return mix(u_c1, u_c2, smoothstep(-w, w, s));
  return mix(mix(u_c1, u_c2, smoothstep(-0.34 - w, -0.34 + w, s)), u_c3, smoothstep(0.34 - w, 0.34 + w, s));
}
// The same as shafts, with a little dark between them.
vec3 lightShaft(float s) {
  if (u_n < 1.5) return u_c1 * exp(-lsq(s / 0.80));
  if (u_n < 2.5) return u_c1 * exp(-lsq((s + 0.50) / 0.37)) + u_c2 * exp(-lsq((s - 0.50) / 0.37));
  return u_c1 * exp(-lsq((s + 0.68) / 0.27)) + u_c2 * exp(-lsq(s / 0.27)) + u_c3 * exp(-lsq((s - 0.68) / 0.27));
}
// Streaks along the rays, drifting slowly.
float streaks(float s, float t) {
  float a = 0.5 + 0.5 * sin(s * 11.0 + 1.6 * sin(t * 0.31) + t * 0.22);
  float b = 0.5 + 0.5 * sin(s * 27.0 - t * 0.37 + 1.3 * sin(s * 6.0 + t * 0.23));
  return 0.62 + 0.26 * a + 0.22 * b * b;
}
float grainAt() { return fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5; }
`;

/* ------------------------------------------------------------------ foil */
export const FOIL_VS = `
in vec2 a;
${COMMON}
uniform vec2 u_size;       // the body
uniform float u_flap;      // the flap's height, in the same units
uniform float u_piece;     // 0 the body, 1 the flap, 2 the body's near side once open, 3 its far side, seen from inside
uniform float u_q;         // how far the flap has been pulled up, 0 to 1
uniform float u_grip;      // where along it the hand holds it
uniform float u_rad;       // the roll of the part pulled up: radius and how far round
uniform float u_curl;
uniform float u_open;      // the mouth
uniform float u_air;       // what air has got in since it was opened
uniform vec2 u_bend;       // the film bowing as it is moved: across, and down
uniform float u_lift;      // the top drawn toward us by the hand
uniform float u_wave;      // the loose flap rippling
uniform float u_crush;     // bent about, once it is let go of
uniform float u_seed;
out vec2 v_uv;
out vec3 v_pos;
out vec3 v_n;
out vec3 v_tx;
out vec3 v_ty;
out float v_up;            // how far above the mouth
// How the near side stands off the far one: closed at the foot and the sides, and at the top until it is opened.
float puff(vec2 p) {
  float x = 1.0 - (2.0 * p.x - 1.0) * (2.0 * p.x - 1.0);
  float y = mix(0.58 * u_open, 1.0, smoothstep(0.0, 0.42, p.y)) * (1.0 - p.y * p.y * p.y * p.y);
  return x * (0.7 + 0.3 * x) * y * (1.0 + 0.03 * sin(p.x * 4.0 + p.y * 3.0 + u_seed));
}
void main() {
  vec2 uv = a;
  vec3 pos = vec3((uv - 0.5) * u_size, 0.0);
  vec3 n = vec3(0.0, 0.0, 1.0), tx = vec3(1.0, 0.0, 0.0), ty = vec3(0.0, 1.0, 0.0);
  if (u_piece > 0.5 && u_piece < 1.5) {
    // Stuck down from the top edge; what is loose rolls up toward us and over, the side in hand first.
    float h = uv.y * u_flap;
    float q = clamp(u_q * 1.3 - 0.3 * abs(uv.x - u_grip), 0.0, 1.0);
    float line = u_flap * (1.0 - q), d = h - line;
    pos.y = -0.5 * u_size.y + h;
    // It lies on the near side, which stands off a little.
    float A = u_air * 17.0 * (1.0 - u_open), e = 0.012;
    vec2 b = vec2(uv.x, min(h, line) / u_size.y);
    float base = 0.9 + A * puff(b);
    vec2 g = A * vec2(puff(b + vec2(e, 0.0)) - puff(b - vec2(e, 0.0)), puff(b + vec2(0.0, e)) - puff(b - vec2(0.0, e))) / (2.0 * e) / u_size;
    pos.z = base;
    n = normalize(vec3(-g, 1.0));
    if (d > 0.0) {
      float th = min(d / u_rad, u_curl), rest = max(0.0, d - u_rad * u_curl);
      pos.y = -0.5 * u_size.y + line + u_rad * sin(th) + rest * cos(th);
      pos.z = base + u_rad * (1.0 - cos(th)) + rest * sin(th);
      n = vec3(0.0, -sin(th), cos(th));
      ty = vec3(0.0, cos(th), sin(th));
      // Loose film is never straight.
      float loose = smoothstep(0.0, 0.8, d / u_flap), w = uv.x * 5.2 + u_seed;
      pos += n * u_wave * loose * (sin(w) + 0.4 * sin(w * 2.3 + 1.0));
      float lean = u_wave * loose * 5.2 * (cos(w) + 0.92 * cos(w * 2.3 + 1.0)) / u_size.x;
      tx = normalize(vec3(1.0, 0.0, 0.0) + n * lean);
      n = normalize(n - vec3(lean, 0.0, 0.0));
    }
  }
  if (u_piece < 0.5 || (u_piece > 1.5 && u_piece < 2.5)) {
    float A = u_air * 17.0, e = 0.012;
    pos.z += A * puff(uv);
    vec2 g = A * vec2(puff(uv + vec2(e, 0.0)) - puff(uv - vec2(e, 0.0)), puff(uv + vec2(0.0, e)) - puff(uv - vec2(0.0, e))) / (2.0 * e) / u_size;
    // The edge of the mouth sags open.
    float sag = u_open * sin(3.14159 * uv.x) * exp(-uv.y / 0.06);
    pos.y += sag * 8.0;
    n = normalize(vec3(-g, 1.0));
    tx = normalize(vec3(1.0, 0.0, g.x));
    ty = normalize(vec3(0.0, 1.0, g.y));
  }
  v_up = -0.5 * u_size.y - pos.y;
  {
    // Soft all over: it bows as it is moved, and the top comes up with the hand.
    vec2 c = pos.xy / u_size;
    float top = clamp(exp(-(c.y + 0.5) / 0.2), 0.0, 1.0);
    pos.z += dot(u_bend, 4.0 * c * c - 0.33) + u_lift * top * (1.0 - 0.6 * abs(uv.x - u_grip));
    vec2 k = 8.0 * u_bend * c / u_size;
    n = normalize(n - vec3(k.x, k.y, 0.0));
    tx = normalize(tx - n * dot(tx, n));
    ty = normalize(ty - n * dot(ty, n));
  }
  if (u_crush > 0.0) {
    // Film does not ball up: it only lies in one slow bend.
    vec2 c = pos.xy / u_size;
    vec2 dir = vec2(0.35, 0.94);
    float f1 = dot(c, dir) * 2.6 + u_seed;
    pos.z += u_crush * sin(f1) * 30.0;
    vec2 k = dir * cos(f1) * 2.6 * 30.0 / u_size;
    n = normalize(n - vec3(k * u_crush, 0.0));
    tx = normalize(tx - n * dot(tx, n));
    ty = normalize(ty - n * dot(ty, n));
  }
  vec4 world = u_model * vec4(pos, 1.0);
  mat3 m = mat3(u_model);
  v_n = m * n;
  v_tx = m * tx;
  v_ty = m * ty;
  v_pos = world.xyz;
  v_uv = uv;
  gl_Position = u_vp * world;
}`;

export const FOIL_FS = `
in vec2 v_uv;
in vec3 v_pos;
in vec3 v_n;
in vec3 v_tx;
in vec3 v_ty;
in float v_up;
uniform sampler2D u_room;
uniform float u_piece;
uniform float u_air;
uniform float u_cut;       // the open flap is drawn in two: 1 what stands above the mouth, 2 what still hangs over the near side
uniform float u_closed;    // 1 while the flap lies on the body: it is drawn as part of it
uniform float u_q;
uniform float u_grip;
uniform float u_full;      // 1 with the card inside
uniform float u_seed;
uniform float u_flip;      // mirrors the film, so bags are not all alike
uniform vec2 u_room_shift;
uniform vec3 u_lamp;       // the pointer as a small lamp
uniform float u_lit;
uniform float u_hint;      // a glint running along the flap's edge; below -1 for none
uniform float u_strain;    // the flap about to give a little more
uniform float u_glow;      // the light inside, as far as it has got out
uniform vec2 u_size;
uniform float u_rad;
out vec4 o_c;
${LIGHT}

// Flat mirror film, cut straight: a body with the card in it, and a flap that folds down over it and sticks.
const vec2 BODY = vec2(62.0, 90.0);
const float FLAP = 18.0;

vec3 room(vec3 r, float lod) {
  vec2 m = r.xy / (1.001 + max(r.z, 0.0));
  // Film pulled along its length shows long streaks: what lies above and below counts for less.
  return textureLod(u_room, m * vec2(0.675, 0.30) + 0.5 + u_room_shift, lod).rgb * 1.06;
}
float sq(float v) { return v * v; }
float cover(float sd) { return clamp(sd / max(fwidth(sd), 1e-5) + 0.5, 0.0, 1.0); }
// A straight crease from a to b: the slope across it.
vec2 fold(vec2 p, vec2 a, vec2 b, float w, float amp) {
  vec2 d = b - a;
  float l = length(d);
  d /= l;
  vec2 c = vec2(-d.y, d.x);
  float u = dot(p - a, d), v = dot(p - a, c);
  float f = smoothstep(-1.0, 3.0, u) * (1.0 - smoothstep(0.3 * l, l, u));
  return c * (amp * f * exp(-v * v / (w * w)) * (-2.0 * v / (w * w)));
}
float ramp(float a, float b, float x, out float d) {
  float t = clamp((x - a) / (b - a), 0.0, 1.0);
  d = 6.0 * t * (1.0 - t) / (b - a);
  return t * t * (3.0 - 2.0 * t);
}
// The film lies nearly flat and loose. It is never quite true; the card makes itself felt only as a soft, uneven rise well
// outside its edges, stronger in some places than in others.
vec2 lie(vec2 p, float full) {
  vec2 s = vec2(
    0.016 * sin(p.y * 0.046 + u_seed) + 0.010 * sin(p.x * 0.10 + p.y * 0.021 + u_seed * 2.0) + 0.006 * sin(p.x * 0.21 - p.y * 0.07 + u_seed * 3.1),
    0.013 * sin(p.x * 0.058 + u_seed * 1.3) + 0.008 * sin(p.y * 0.085 + u_seed * 2.3) + 0.005 * sin(p.y * 0.17 + p.x * 0.06 + u_seed));
  vec2 w = p + vec2(1.3 * sin(p.y * 0.075 + u_seed) + 0.5 * sin(p.y * 0.22 + u_seed * 2.0), 1.2 * sin(p.x * 0.09 + u_seed * 1.7) + 0.4 * sin(p.x * 0.27 + u_seed));
  float dl, dr, dt, db;
  float l = ramp(0.5, 7.5, w.x, dl), r = 1.0 - ramp(54.5, 61.5, w.x, dr), t = ramp(0.5, 9.0, w.y, dt), b = 1.0 - ramp(81.5, 89.5, w.y, db);
  float some = 0.65 + 0.35 * sin(p.x * 0.07 + p.y * 0.052 + u_seed * 2.7);
  s += 0.17 * full * some * vec2((dl * r - l * dr) * t * b, (dt * b - t * db) * l * r);
  // Opened, the film puckers a little along the sides and at the mouth, and keeps two creases from being held.
  float used = 1.0 - full, side = min(p.x, 62.0 - p.x);
  float py = p.y * 0.70 + 1.6 * sin(p.y * 0.17 + u_seed) + u_seed * 3.0 + (p.x > 31.0 ? 2.1 : 0.0);
  // Only here and there along an edge, and not alike on the two sides.
  float here = smoothstep(0.15, 0.85, sin(p.y * 0.105 + u_seed * 1.9 + (p.x > 31.0 ? 2.6 : 0.0)));
  s.y += used * here * 0.065 * exp(-side / 2.8) * sin(py);
  s.x += used * 0.016 * exp(-max(p.y, 0.0) / 5.0) * sin(p.x * 0.45 + u_seed * 1.7);
  s += used * (fold(p, vec2(7.0 + 3.0 * sin(u_seed), 3.0), vec2(22.0, 50.0), 1.0, 0.10) + fold(p, vec2(59.0, 74.0 + 5.0 * sin(u_seed * 2.0)), vec2(38.0, 86.0), 0.9, 0.08));
  return s;
}

void main() {
  bool flap = u_piece > 0.5 && u_piece < 1.5, front = u_piece > 1.5 && u_piece < 2.5, far = u_piece > 2.5;
  vec2 mm = v_uv * vec2(BODY.x, flap ? FLAP : BODY.y);
  float sides = min(mm.x, BODY.x - mm.x);
  float alpha = cover(min(min(mm.y + 0.02, (flap ? FLAP : BODY.y) - mm.y), sides - 0.05 - 0.03 * sin(mm.y * 0.5 + u_seed)));
  if (alpha < 0.02) discard;
  if (u_cut > 0.5 && (u_cut < 1.5 ? v_up < 0.0 : v_up >= 0.0)) discard;

  vec2 at = u_flip > 0.5 ? vec2(BODY.x - mm.x, mm.y) : mm;
  vec2 ns = -lie(flap ? vec2(at.x, at.y * 0.8 - 30.0) : at, flap ? 1.0 : u_full) * vec2(u_flip > 0.5 ? -1.0 : 1.0, 1.0);
  vec3 V = normalize(vec3(0.0, 0.0, 1500.0) - v_pos);
  vec3 N = normalize(v_n + normalize(v_tx) * ns.x + normalize(v_ty) * ns.y);
  bool reverse = !gl_FrontFacing;
  if (reverse) N = -N;
  vec3 R = reflect(-V, N);
  vec3 L = normalize(u_lamp - v_pos);
  float hl = max(dot(N, normalize(L + V)), 0.0);
  float fall = exp(-dot(u_lamp.xy - v_pos.xy, u_lamp.xy - v_pos.xy) / 52000.0);
  float q = clamp(u_q * 1.3 - 0.3 * abs(v_uv.x - u_grip), 0.0, 1.0);
  float line = FLAP * (1.0 - q);
  vec3 col;
  if (far) {
    // Inside: the same film, in the dark of the bag.
    col = (room(R, 4.0) * 0.6 + 0.12) * mix(0.60, 0.13, clamp(mm.y / 6.0, 0.0, 1.0));
  } else if (flap && reverse) {
    // The flap's inside, seen once it is up: the same film from its duller side.
    float y = FLAP - mm.y;
    col = room(R, 1.4) * 0.74 + 0.17;
    col += 0.16 * (1.0 - smoothstep(0.0, 0.35, y));
    col *= 1.0 - 0.20 * exp(-(FLAP - y) / 0.8);
  } else {
    col = reverse ? room(R, 2.0) * 0.92 : mix(room(R, 1.2), room(R, 4.8), 0.42) * vec3(0.985, 0.988, 1.0);
    // Mirror film, but not a mirror: the darks and the lights both keep something of its own silver.
    col = 0.56 + (col - 0.56) * 0.80;
    col += 0.08 * pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 4.0);
    if (flap) col += 0.20 * (1.0 - smoothstep(0.0, 0.35, FLAP - mm.y));
    else if (front) col += 0.20 * (1.0 - smoothstep(0.0, 0.35, mm.y));
    else if (u_closed > 0.5) {
      // The flap's free edge, and the hair of shade under it.
      col += 0.20 * exp(-sq((mm.y - FLAP + 0.2) / 0.16));
      col *= 1.0 - 0.30 * step(FLAP, mm.y) * exp(-(mm.y - FLAP) / 0.7);
    } else {
      col *= 1.0 - 0.34 * smoothstep(0.0, 0.05, q) * exp(-sq((mm.y - line - 1.0) / 3.6));
      col *= 1.0 - 0.30 * (1.0 - smoothstep(0.0, 0.05, q)) * step(FLAP, mm.y) * exp(-(mm.y - FLAP) / 0.7);
    }
  }
  if (!far) {
    col += (pow(hl, 2400.0) * 0.28 + pow(hl, 70.0) * 0.05) * fall * vec3(1.0, 0.98, 0.95);
    col *= 1.0 - 0.14 * exp(-sq((sides - 1.0) / 0.20));
    if (u_hint > -1.0 && !flap) col += exp(-sq((v_uv.x - u_hint) * 7.0)) * exp(-sq((mm.y - 16.5) / 2.6)) * vec3(1.0, 0.98, 0.94) * 0.5;
    // Where the flap is about to give, the film blanches.
    if (flap && !reverse) col += u_strain * 0.22 * exp(-sq((mm.y - line) / 1.6)) * exp(-sq((v_uv.x - u_grip) * 2.4));
  }
  col *= u_lit;
  if (u_glow > 0.003) {
    // Light on the film: what the flap uncovers, the flap's inside, the inside of the bag, the lip.
    float s = v_uv.x * 2.0 - 1.0, on = 0.0, hot = 0.0;
    vec3 tone = lightBand(s, 0.20);
    if (far) {
      col = mix(col, tone * 1.02 + 0.10, u_glow * 0.94);
      hot = 0.30;
    } else if (flap) {
      float d = mm.y - line;
      if (reverse) { on = step(0.0, d) * exp(-max(d, 0.0) / 11.0); hot = 0.5 * exp(-sq(d / 2.4)); }
    } else if (front) {
      on = 0.50 * exp(-mm.y / 3.4);
      hot = 0.9 * exp(-mm.y / 0.5);
    } else {
      // It comes out from under the roll of the flap and runs down over the film.
      float d = mm.y - line - 0.62 * u_rad * BODY.x / u_size.x, open = smoothstep(0.0, 0.12, q) * step(line, mm.y);
      on = open * exp(-max(d, 0.0) / 16.0);
      hot = open * 0.55 * exp(-sq(d / 2.2));
    }
    float k = clamp(on * u_glow, 0.0, 1.0);
    col = mix(col, tone * (0.34 + 0.92 * col), k * 0.9) + (tone * 0.8 + 0.2) * hot * u_glow * 0.5;
  }
  // Bright parts roll off, so the film still shows in them.
  col = mix(col, 1.0 - 0.28 * exp(-(col - 0.72) / 0.28), step(0.72, col));
  o_c = vec4(clamp(col, 0.0, 1.0), alpha);
}`;

/* ------------------------------------------------------------------ card */
export const CARD_VS = `
in vec2 a;
${COMMON}
uniform vec2 u_dim;        // the card, in design units
uniform float u_bend;      // a springy bow along the height
uniform float u_thick;
uniform float u_face;      // 1 the front, -1 the back
uniform float u_rim;       // 0 a face; 1 to 4 the cut edges: left, right, top, bottom
out vec2 v_uvi;
out vec3 v_pos;
out vec3 v_nn;
void main() {
  vec2 p = (a - 0.5) * u_dim;
  vec3 pos = vec3(p, u_face * u_thick * 0.5);
  vec3 n = vec3(0.0, 0.0, 1.0);
  if (u_rim > 0.5) {
    float side = mod(u_rim, 2.0) > 0.5 ? -1.0 : 1.0;
    p = u_rim < 2.5 ? vec2(side * 0.5 * u_dim.x, (a.x - 0.5) * u_dim.y) : vec2((a.x - 0.5) * u_dim.x, side * 0.5 * u_dim.y);
    n = u_rim < 2.5 ? vec3(side, 0.0, 0.0) : vec3(0.0, side, 0.0);
    pos = vec3(p, (a.y - 0.5) * u_thick);
  }
  if (u_bend != 0.0) {
    float y = p.y / u_dim.y * 2.0;
    pos.z += u_bend * (1.0 - y * y);
    n = normalize(n + vec3(0.0, u_bend * 4.0 * y / u_dim.y, 0.0));
  }
  vec4 world = u_model * vec4(pos, 1.0);
  v_nn = mat3(u_model) * n;
  v_pos = world.xyz;
  v_uvi = a;
  gl_Position = u_vp * world;
}`;

/** The card's cut edge: pale board between two printed sheets. */
export const RIM_FS = `
in vec2 v_uvi;
in vec3 v_pos;
in vec3 v_nn;
uniform sampler2D u_noise;
uniform float u_lit;
uniform float u_lip;
uniform float u_lipOn;
out vec4 o_c;
void main() {
  vec3 N = normalize(v_nn);
  float diff = 0.64 + 0.30 * max(dot(N, normalize(vec3(-0.35, -0.75, 0.75))), 0.0);
  float ply = 1.0 - 0.16 * smoothstep(0.30, 0.46, abs(v_uvi.y - 0.5));
  float grain = texture(u_noise, vec2(v_uvi.x * 3.0, v_uvi.y * 0.04)).r - 0.5;
  vec3 col = vec3(0.95, 0.94, 0.965) * diff * ply * (1.0 + grain * 0.06);
  col *= mix(1.0, 0.35 + 0.65 * smoothstep(0.0, 34.0, u_lip - v_pos.y), u_lipOn);
  o_c = vec4(clamp(col * u_lit, 0.0, 1.0), 1.0);
}`;

/** The card's fragment shader, from the page the finishes are looked at on. */
export function cardFs(page) {
  const found = page.match(/const FRAG = `([\s\S]*?)`;/);
  if (!found) throw new Error("card shader not found");
  let s = found[1];
  const swap = (from, to) => {
    if (!s.includes(from)) throw new Error(`card shader changed: ${from}`);
    s = s.split(from).join(to);
  };
  swap("precision highp float;", "");
  swap("varying vec2 v_uv;", `
in vec2 v_uvi;
in vec3 v_pos;
in vec3 v_nn;
uniform sampler2D u_baseB;
uniform sampler2D u_matB;
uniform float u_lit;
uniform float u_lip;       // card pixels above the bag's mouth are lit, those just over it lie in its shade
uniform float u_lipOn;
uniform float u_sheen;     // a band of light crossing the face, -0.5 to 1.5
uniform float u_sheenAmt;
uniform vec3 u_tone;
uniform float u_flash;
uniform float u_lipLight;  // the light it stands in there
out vec4 o_c;
${LIGHT}
vec2 v_uv;
float u_back;`);
  swap("uniform float u_back;\n", "\n");
  s = s.replace(/texture2D\(u_base,\s*/g, "pickBase(").replace(/texture2D\(u_mat,\s*/g, "pickMat(").replace("texture2D(u_sign, at)", "texture(u_sign, at, -0.6)").replace(/texture2D/g, "texture");
  swap("void main() {", `
vec4 pickBase(vec2 p) { return u_back > 0.5 ? texture(u_baseB, p, -0.6) : texture(u_base, p, -0.6); }
vec4 pickMat(vec2 p) { return u_back > 0.5 ? texture(u_matB, p, -0.6) : texture(u_mat, p, -0.6); }
void main() {
  u_back = gl_FrontFacing ? 0.0 : 1.0;
  v_uv = gl_FrontFacing ? v_uvi : vec2(1.0 - v_uvi.x, v_uvi.y);`);
  const out = s.match(/gl_FragColor = vec4\((.*), 1\.0\);/);
  if (!out) throw new Error("card shader output not found");
  swap(out[0], `
  vec3 fin = ${out[1]};
  vec3 nn = normalize(v_nn);
  float facing = abs(nn.z);
  fin *= 0.72 + 0.28 * smoothstep(0.0, 0.92, facing);
  float sweep = (v_uv.x * 0.72 + v_uv.y * 0.42) - u_sheen;
  fin += u_sheenAmt * (exp(-sweep * sweep * 90.0) * 0.75 + exp(-sweep * sweep * 14.0) * 0.18) * mix(vec3(1.0), u_tone, 0.35);
  float over = u_lip - v_pos.y;
  fin *= mix(1.0, 0.35 + 0.65 * smoothstep(0.0, 34.0, over), u_lipOn);
  if (u_lipLight > 0.003) {
    float lk = u_lipLight * u_lipOn * exp(-max(over, 0.0) / 78.0);
    vec3 lt = lightBand(v_pos.x / 110.0, 0.24);
    fin = mix(fin, lt * (0.30 + 0.95 * fin), clamp(lk, 0.0, 1.0) * 0.85) + lt * lk * 0.34;
  }
  fin = mix(fin, vec3(1.0), u_flash);
  o_c = vec4(clamp(fin * u_lit, 0.0, 1.0), 1.0);`);
  return s;
}

/* ------------------------------------------------------------------ box */
export const BOX_VS = `
in vec2 a;
${COMMON}
uniform vec2 u_dim;
uniform vec4 u_print;      // the part of the print atlas on this face
uniform vec4 u_fold;       // sides that turn into a rounded fold: left, right, top, bottom
uniform float u_radius;
uniform float u_bow;       // board is never quite flat
out vec2 v_uv;
out vec2 v_at;
out vec3 v_pos;
out vec3 v_n;
out vec2 v_tex;
// The outer fifth of the grid on each side lies on the fold: its half of a quarter turn.
float lay(float s, float h, float lo, float hi, out float lean) {
  float f = s < 0.0 ? lo : hi;
  float k = clamp((abs(s) - 0.3) / 0.2, 0.0, 1.0);
  lean = sign(s) * tan(k * 0.785398) * f;
  return clamp(s / 0.3, -1.0, 1.0) * (h - u_radius * f);
}
void main() {
  vec2 s = a - 0.5, lean;
  vec2 p = vec2(lay(s.x, u_dim.x * 0.5, u_fold.x, u_fold.y, lean.x), lay(s.y, u_dim.y * 0.5, u_fold.z, u_fold.w, lean.y));
  vec3 n = normalize(vec3(lean, 1.0));
  vec3 pos = vec3(p, -u_radius) + u_radius * n;
  vec4 world = u_model * vec4(pos, 1.0);
  v_at = pos.xy;
  v_uv = pos.xy / u_dim + 0.5;
  v_tex = mix(u_print.xy, u_print.zw, v_uv);
  v_pos = world.xyz;
  v_n = mat3(u_model) * normalize(n + vec3(u_bow * pos.xy / (u_dim * 0.5), 0.0));
  gl_Position = u_vp * world;
}`;

export const BOX_FS = `
in vec2 v_uv;
in vec2 v_at;
in vec3 v_pos;
in vec3 v_n;
in vec2 v_tex;
uniform sampler2D u_ink;
uniform sampler2D u_noise;
uniform vec2 u_dim;
uniform float u_inked;
uniform float u_lit;
uniform vec3 u_lamp;
uniform float u_dark;      // inside: how dark toward the bottom
uniform float u_edge;      // the board's cut edge
uniform vec4 u_fold;
uniform vec2 u_corner;     // rounded corners of a flap: top, bottom
out vec4 o_c;
void main() {
  vec3 N = normalize(v_n);
  if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(vec3(0.0, 0.0, 1500.0) - v_pos);
  vec3 L = normalize(vec3(-0.35, -0.75, 0.75));
  vec3 P = normalize(u_lamp - v_pos);
  float diff = 0.60 + 0.34 * max(dot(N, L), 0.0) + 0.14 * max(dot(N, P), 0.0);
  float grain = texture(u_noise, v_at / 5.0).r - 0.5;
  vec3 col;
  if (u_edge > 0.5) {
    // Pressed pulp: pale, with faint layers.
    col = vec3(0.80, 0.775, 0.81) * diff * (1.0 + grain * 0.10);
  } else if (gl_FrontFacing) {
    vec3 ground = vec3(0.575, 0.430, 0.775) * (1.0 + grain * 0.05);
    float ink = u_inked * texture(u_ink, v_tex).r;
    col = ground * diff;
    col = mix(col, vec3(0.985, 0.97, 0.985) * min(1.0, diff * 1.22), ink);
    // A matte lamination: a wide, faint sheen.
    float sp = pow(max(dot(N, normalize(P + V)), 0.0), 14.0);
    float sp2 = pow(max(dot(N, normalize(L + V)), 0.0), 8.0);
    col += (sp * 0.16 + sp2 * 0.10) * vec3(1.0, 0.95, 1.0);
    // The folds are a little rubbed, here and there.
    vec4 e = vec4(v_at.x, -v_at.x, v_at.y, -v_at.y) + 0.5 * u_dim.xxyy;
    vec4 near = u_fold * (1.0 - smoothstep(vec4(0.4), vec4(4.6), e));
    float worn = max(max(near.x, near.y), max(near.z, near.w));
    float rub = smoothstep(-0.12, 0.34, texture(u_noise, v_at / 41.0).r - 0.5 + grain * 0.45);
    col = mix(col, vec3(0.78, 0.71, 0.86) * diff, worn * (0.10 + 0.22 * rub));
  } else {
    col = vec3(0.90, 0.89, 0.90) * diff * mix(1.0, 0.42, u_dark * v_uv.y) * (1.0 + grain * 0.04);
  }
  float alpha = 1.0;
  float cr = v_at.y < 0.0 ? u_corner.x : u_corner.y;
  if (cr > 0.0) {
    vec2 cq = abs(v_at) - 0.5 * u_dim + cr;
    if (min(cq.x, cq.y) > 0.0) { float cd = cr - length(cq); alpha = clamp(cd / max(fwidth(cd), 1e-4) + 0.5, 0.0, 1.0); }
    if (alpha < 0.02) discard;
  }
  o_c = vec4(clamp(col * u_lit, 0.0, 1.0), alpha);
}`;

/* ------------------------------------------------------------------ flat things */
export const FLAT_VS = `
in vec2 a;
${COMMON}
uniform vec2 u_dim;
uniform vec4 u_rect;
out vec2 v_uv;
out vec2 v_tex;
out vec3 v_n;
void main() {
  v_uv = a;
  v_tex = mix(u_rect.xy, u_rect.zw, a);
  v_n = mat3(u_model) * vec3(0.0, 0.0, 1.0);
  gl_Position = u_vp * u_model * vec4((a - 0.5) * u_dim, 0.0, 1.0);
}`;

export const SHADOW_FS = `
in vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_alpha;
out vec4 o_c;
void main() { o_c = vec4(0.0, 0.0, 0.0, texture(u_tex, v_uv).r * u_alpha); }`;

export const THUMB_FS = `
in vec2 v_uv;
in vec2 v_tex;
in vec3 v_n;
uniform sampler2D u_tex;
uniform float u_lit;
uniform float u_gleam;
uniform float u_solid;
uniform sampler2D u_sign;
uniform vec4 u_signBox;    // the signature's place on the card, 0 to 1: left, top, width, height; no width, no signature
out vec4 o_c;
void main() {
  vec3 c = texture(u_tex, v_tex, -0.5).rgb;
  vec2 at = (v_uv - u_signBox.xy) / max(u_signBox.zw, vec2(1e-3));
  vec3 sg = texture(u_sign, at, -0.6).rgb;
  if (u_solid > 0.5) { o_c = vec4(vec3(0.70, 0.68, 0.72) * u_lit, 1.0); return; }
  float ink = step(1e-3, u_signBox.z) * step(0.0, at.x) * step(at.x, 1.0) * step(0.0, at.y) * step(at.y, 1.0);
  c = mix(c, vec3(0.20, 0.11, 0.03), ink * 0.40 * clamp(1.2 - (sg.b - 0.5) * 24.0, 0.0, 1.0));
  c = mix(c, vec3(0.80, 0.60, 0.23), ink * sg.r);
  float band = v_uv.x * 0.8 + v_uv.y * 0.5 - u_gleam;
  c += exp(-band * band * 40.0) * 0.35;
  o_c = vec4(c * u_lit, 1.0);
}`;

/** The desk: dark, lit by a lamp, with the room's colours at its edges. */
export const DESK_FS = `
in vec2 v_uv;
uniform vec2 u_view;
uniform sampler2D u_noise;
uniform float u_spot;      // 1: everything but the middle falls dark
uniform float u_toneAmt;
uniform vec2 u_lampAt;
out vec4 o_c;
${LIGHT}
void main() {
  vec2 p = (v_uv - 0.5) * u_view;
  vec3 tone = lightBand(p.x / 240.0, 0.75);
  float d = length((p - vec2(0.0, -30.0)) / vec2(560.0, 400.0));
  vec3 col = mix(vec3(0.245, 0.205, 0.300), vec3(0.088, 0.072, 0.115), smoothstep(0.0, 1.25, d));
  col += vec3(0.13, 0.055, 0.045) * exp(-dot(p - vec2(-520.0, 330.0), p - vec2(-520.0, 330.0)) / 160000.0);
  col += vec3(0.055, 0.045, 0.14) * exp(-dot(p - vec2(540.0, -300.0), p - vec2(540.0, -300.0)) / 170000.0);
  col += vec3(0.030, 0.026, 0.036) * exp(-dot(p - u_lampAt, p - u_lampAt) / 60000.0);
  float g = texture(u_noise, p / 3.1).r + texture(u_noise, p / 7.7 + 0.3).g - 1.0;
  col *= 1.0 + g * 0.07;
  vec3 spot = vec3(0.040, 0.033, 0.054) + (tone * 0.16 + vec3(0.05)) * exp(-dot(p, p) / 90000.0);
  col = mix(col, spot, u_spot * 0.92);
  col += tone * u_toneAmt * (0.10 + 0.22 * exp(-dot(p, p) / 120000.0));
  col += (texture(u_noise, v_uv * u_view / 1.7).b - 0.5) / 160.0;
  o_c = vec4(col, 1.0);
}`;

/** Rays behind a card that earned them. */
export const RAYS_FS = `
in vec2 v_uv;
uniform float u_time;
uniform float u_amt;
out vec4 o_c;
${LIGHT}
void main() {
  vec2 p = v_uv * 2.0 - 1.0;
  float r = length(p), a = atan(p.y, p.x);
  float ray = 0.5 + 0.5 * sin(a * 9.0 + u_time * 0.35) * sin(a * 5.0 - u_time * 0.22 + 1.3);
  ray = pow(ray, 2.2);
  float body = exp(-r * r * 5.0) * 0.55 + ray * exp(-r * 2.6) * (1.0 - smoothstep(0.75, 1.0, r));
  o_c = vec4(lightBand(p.x / 0.42, 0.34) * body * u_amt + grainAt() / 255.0, 0.0);
}`;

/** Light that gets out from under the flap while it is being pulled up. */
export const SLIT_FS = `
in vec2 v_uv;
uniform vec2 u_dim;
uniform vec2 u_bag;        // the bag's width, and where its top lies below the top of this
uniform float u_flap;
uniform float u_q;
uniform float u_grip;
uniform float u_rad;
uniform float u_amt;
uniform float u_time;
out vec4 o_c;
${LIGHT}
void main() {
  vec2 p = vec2((v_uv.x - 0.5) * u_dim.x, v_uv.y * u_dim.y - u_bag.y);
  float ux = p.x / u_bag.x;
  float q = clamp(u_q * 1.3 - 0.3 * abs(clamp(ux + 0.5, 0.0, 1.0) - u_grip), 0.0, 1.0);
  // Its roll hides where the flap is still held: the light shows along the roll's lower edge.
  float d = p.y - u_flap * (1.0 - q) - 0.62 * u_rad * (1.0 - smoothstep(0.92, 1.0, q) * 0.5);
  float open = smoothstep(0.0, 0.14, q);
  float s = ux * 2.0 * 190.0 / (190.0 + max(d, 0.0));
  float side = 1.0 - smoothstep(0.86, 1.22, abs(s));
  float ray = streaks(s * 1.3, u_time);
  float down = exp(-max(d, 0.0) / 52.0) * ray, up = exp(min(d, 0.0) / 11.0);
  float halo = exp(-abs(d) / 26.0) * 0.30 * (1.0 - smoothstep(0.9, 1.7, abs(ux * 2.0)));
  float amt = (down * up * side + halo) * open;
  float hot = exp(-lsq(d / 4.2)) * side * open;
  vec3 tone = lightShaft(clamp(s, -1.0, 1.0)) * 0.55 + lightBand(s, 0.20) * 0.45;
  vec3 col = 1.0 - exp(-(tone * amt * 1.35 + (tone * 0.7 + 0.3) * hot * 0.65) * u_amt);
  float fade = smoothstep(0.0, 0.12, v_uv.x) * smoothstep(0.0, 0.12, 1.0 - v_uv.x) * smoothstep(0.0, 0.10, v_uv.y) * smoothstep(0.0, 0.16, 1.0 - v_uv.y);
  o_c = vec4((col + grainAt() / 255.0) * fade, clamp(amt * u_amt * 0.45, 0.0, 0.7) * fade);
}`;

/** Light out of the open mouth: it comes from some way down inside, so it fans out, a shaft for each colour. */
export const BEAM_FS = `
in vec2 v_uv;
uniform vec2 u_dim;
uniform float u_mouth;     // where on this the mouth lies, 0 to 1
uniform float u_half;      // half the mouth's width
uniform float u_deep;      // how far down the light is
uniform float u_reach;
uniform float u_amt;
uniform float u_time;
out vec4 o_c;
${LIGHT}
void main() {
  float x = (v_uv.x - 0.5) * u_dim.x, y = (u_mouth - v_uv.y) * u_dim.y, up = max(y, 0.0);
  float k = u_deep / (u_deep + up);
  float s = x * k / u_half;
  // The sides soften the further up it goes.
  float soft = 0.05 + 0.55 * (1.0 - k);
  float side = 1.0 - smoothstep(1.0 - soft, 1.0 + 0.6 * soft, abs(s));
  float fall = exp(-up / u_reach) * (0.55 + 0.45 * k);
  float below = y < 0.0 ? exp(y / 13.0) * 0.55 : 1.0;
  float amt = side * fall * below * streaks(s, u_time);
  float halo = exp(-length(vec2(max(abs(x) - u_half * 0.8, 0.0), y * 1.15)) / 46.0) * 0.26;
  float hot = exp(-lsq(y / 7.0)) * (1.0 - smoothstep(0.82, 1.04, abs(x) / u_half));
  vec3 col = lightShaft(s) * amt + lightBand(clamp(x / u_half, -1.0, 1.0), 0.24) * (halo + 0.75 * hot) + 0.16 * hot;
  col = 1.0 - exp(-col * u_amt * 1.15);
  float fade = smoothstep(0.0, 0.12, v_uv.x) * smoothstep(0.0, 0.12, 1.0 - v_uv.x) * smoothstep(0.0, 0.22, v_uv.y) * smoothstep(0.0, 0.06, 1.0 - v_uv.y);
  o_c = vec4((col + grainAt() / 255.0) * fade, clamp((amt + halo) * u_amt * 0.42, 0.0, 0.7) * fade);
}`;

export const WASH_FS = `
in vec2 v_uv;
uniform vec4 u_color;
uniform float u_round;
out vec4 o_c;
void main() {
  float r = length((v_uv - 0.5) * 2.0);
  float k = mix(1.0, exp(-r * r * 2.2), u_round);
  o_c = vec4(u_color.rgb * u_color.a * k, u_color.a * k);
}`;

/* ------------------------------------------------------------------ particles */
export const BIT_VS = `
in vec2 a;
in vec4 b;   // where, size, kind
in vec4 c;   // colour, spin
uniform mat4 u_vp;
out vec2 v_q;
out vec4 v_c;
out float v_kind;
void main() {
  float s = sin(c.w), k = cos(c.w);
  vec2 q = a;
  // A flake turns in the air: it narrows as it goes edge on.
  if (b.w < 0.5) q.x *= abs(cos(c.w * 2.3)) * 0.85 + 0.15;
  vec2 r = vec2(q.x * k - q.y * s, q.x * s + q.y * k);
  gl_Position = u_vp * vec4(b.xy + r * b.z, 40.0, 1.0);
  v_q = a;
  v_c = vec4(c.rgb, abs(cos(c.w * 2.3)));
  v_kind = b.w;
}`;
export const BIT_FS = `
in vec2 v_q;
in vec4 v_c;
in float v_kind;
out vec4 o_c;
void main() {
  vec2 q = v_q * 2.0;
  if (v_kind < 0.5) {
    // A sliver of foil.
    float m = step(abs(q.x) * 1.3 + abs(q.y) * 0.8, 0.82 + 0.2 * q.x * q.y);
    if (m < 0.5) discard;
    o_c = vec4(v_c.rgb * (0.30 + 1.0 * v_c.a * v_c.a), 1.0);
  } else {
    float r = dot(q, q);
    float star = v_kind > 1.5 ? 0.0 : exp(-abs(q.x) * 14.0 - abs(q.y) * 2.6) + exp(-abs(q.y) * 14.0 - abs(q.x) * 2.6);
    float k = (exp(-r * 22.0) + star * 0.7) * (1.0 - smoothstep(0.75, 1.0, r));
    o_c = vec4(v_c.rgb * k, 0.0);
  }
}`;
