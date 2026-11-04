// Derives the accent tokens of tokens.css from one color, so a subtree can wear another palette.
type Rgb = [number, number, number];

const INK = "#2B2530";
const WHITE = "#FFFFFF";
/** --page in tokens.css: small accent text sits on it. */
const PAGE = "#FFF4EE";
const AA = 4.5;

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

export function accentTokens(color: string): Record<string, string> {
  const onAccent = contrast(color, INK) >= contrast(color, WHITE) ? INK : WHITE;
  const accent = untilReadable(color, onAccent === INK ? WHITE : INK, onAccent);
  return {
    "--accent": accent,
    "--accent-rgb": rgb(accent).join(", "),
    "--accent-deep": untilReadable(accent, INK, PAGE),
    "--accent-hover": mix(accent, WHITE, 0.18),
    "--accent-soft": mix(accent, WHITE, 0.74),
    "--accent-tint": mix(accent, WHITE, 0.9),
    "--on-accent": onAccent,
  };
}
