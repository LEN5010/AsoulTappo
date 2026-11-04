// Theme skin: maps the Bilibili-style dress-up parts of a theme onto the UI.
//   panel background <- portrait backgrounds (cycled per tab) under a glass overlay
//   header           <- head_bg       tab bar <- tail_bg + tail icons
//   profile banner   <- banner        like animation <- thumbup      connecting <- loading
// Every part is optional: a missing part falls back to a gradient made of the theme colors.
import { characterColor, getTheme, resolveAsset, type ManifestTheme } from "./manifest";

export interface Skin {
  vars: Record<string, string>;
  headBg: string;
  tabBg: string;
  banner: string;
  backgrounds: string[];
  thumbup: string;
  loading: string;
  icons: Record<string, { n: string; s: string }>;
}

/** "#rrggbb" -> "r, g, b" for use inside rgba(var(--x-rgb), a). */
export function hexToRgb(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return "255, 107, 157";
  const n = parseInt(m[1], 16);
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
}

/** Whether a text color on top of `hex` should be light. */
export function isDark(hex: string): boolean {
  const [r, g, b] = hexToRgb(hex).split(",").map(Number);
  return 0.299 * r + 0.587 * g + 0.114 * b < 150;
}

export function buildSkin(themeId: string, character: string, serverBase: string, appBase = "/"): Skin {
  const t: ManifestTheme = getTheme(themeId);
  const url = (r?: string | null) => resolveAsset(r, serverBase, appBase);
  const accent = t.colors.accent;
  const who = characterColor(character);
  const icons: Skin["icons"] = {};
  for (const [k, v] of Object.entries(t.icons)) icons[k] = { n: url(v.n), s: url(v.s) };
  return {
    vars: {
      "--accent": accent,
      "--accent-rgb": hexToRgb(accent),
      "--on-accent": isDark(accent) ? "#fff" : "#2b2020",
      "--head-fg": t.colors.headFg ?? (isDark(accent) ? "#fff" : "#2b2020"),
      "--tab-fg": t.colors.tabFg ?? "#2b2020",
      "--tint": t.colors.tint,
      "--tint-rgb": hexToRgb(t.colors.tint),
      "--char": who,
      "--char-rgb": hexToRgb(who),
      "--on-char": isDark(who) ? "#fff" : "#2B2530",
    },
    headBg: url(t.parts.headBg),
    tabBg: url(t.parts.tabBg),
    banner: url(t.parts.banner),
    backgrounds: (t.parts.backgrounds ?? []).map(url),
    thumbup: url(t.parts.thumbup),
    loading: url(t.parts.loading),
    icons,
  };
}

/** Pick the panel background for tab index i (cycles; "" when the theme has none). */
export function backgroundFor(skin: Pick<Skin, "backgrounds">, i: number): string {
  const n = skin.backgrounds.length;
  return n ? skin.backgrounds[((i % n) + n) % n] : "";
}

/** CSS `background-image` value with a graceful fallback when an image is missing. */
export function cssImage(u: string): string {
  return u ? `url("${u}")` : "none";
}
