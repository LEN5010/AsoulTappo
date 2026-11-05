// Derives the color tokens of tokens.css from one color, so the app can wear another palette.
type Rgb = [number, number, number];

const INK = "#2B2530";
const WHITE = "#FFFFFF";
/** --ink-3 in tokens.css: the faintest text that sits on the page. */
const INK_3 = "#766D7C";
const AA = 4.5;
const WARM_SHIFT = 18;

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Rgb;
const toHex = (c: Rgb) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`.toUpperCase();

function mix(from: string, to: string, t: number): string {
  const a = rgb(from);
  const b = rgb(to);
  return toHex(a.map((v, i) => v + (b[i]! - v) * t) as Rgb);
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as Rgb;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** Steps `color` toward `target` until it reaches AA contrast with `against`. */
function untilReadable(color: string, target: string, against: string): string {
  for (let t = 0; t <= 1; t += 0.04) {
    const next = mix(color, target, t);
    if (contrast(next, against) >= AA) return next;
  }
  return target;
}

function hueSaturation(hex: string): [number, number] {
  const [r, g, b] = rgb(hex).map((v) => v / 255) as Rgb;
  const hi = Math.max(r, g, b);
  const lo = Math.min(r, g, b);
  const d = hi - lo;
  if (!d) return [0, 0];
  const sector = hi === r ? ((g - b) / d + 6) % 6 : hi === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [sector * 60, d / (1 - Math.abs(hi + lo - 1))];
}

function hslToHex(h: number, s: number, l: number): string {
  const channel = (n: number) => {
    const k = (n + h / 30) % 12;
    return 255 * (l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1)));
  };
  return toHex([channel(0), channel(8), channel(4)]);
}

/** Text tone of `color`: warm hues slide toward rose, because plainly darker orange or pink reads as brown. */
function deepTone(color: string, against: string): string {
  const [hue, saturation] = hueSaturation(color);
  const warm = hue < 50 || hue > 330;
  const h = warm ? (hue + 360 - WARM_SHIFT) % 360 : hue;
  const s = warm ? Math.max(saturation, 0.6) : saturation;
  for (let l = 0.62; l > 0.15; l -= 0.01) {
    const next = hslToHex(h, s, l);
    if (contrast(next, against) >= AA) return next;
  }
  return untilReadable(color, INK, against);
}

export function accentTokens(color: string, tones?: { top: string; bottom: string }): Record<string, string> {
  const onAccent = contrast(color, INK) >= contrast(color, WHITE) ? INK : WHITE;
  const accent = untilReadable(color, onAccent === INK ? WHITE : INK, onAccent);
  const page = untilReadable(mix(accent, WHITE, 0.93), WHITE, INK_3);
  return {
    "--accent": accent,
    "--accent-rgb": rgb(accent).join(", "),
    "--accent-surface": accent,
    "--on-accent-surface": onAccent,
    ...(tones && { "--tone-top": tones.top, "--tone-bottom": tones.bottom }),
    "--accent-deep": deepTone(accent, page),
    "--accent-hover": untilReadable(mix(accent, WHITE, 0.18), accent, onAccent),
    "--accent-mid": mix(accent, WHITE, 0.45),
    "--accent-soft": mix(accent, WHITE, 0.74),
    "--accent-tint": mix(accent, WHITE, 0.9),
    "--on-accent": onAccent,
    "--page": page,
    "--line": mix(accent, WHITE, 0.84),
    "--line-2": mix(accent, WHITE, 0.72),
  };
}
