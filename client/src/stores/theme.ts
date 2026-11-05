import { computed, ref, watch } from "vue";
import { manifest } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { buildSkin } from "../skin";
import { accentTokens } from "../ui/palette";
import { settings } from "./settings";

export const reducedMotion = ref(false);
if (typeof window !== "undefined" && window.matchMedia) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  reducedMotion.value = mq.matches;
  mq.addEventListener?.("change", (e) => (reducedMotion.value = e.matches));
}

export const skin = computed(() =>
  buildSkin("jiaran-eat", settings.character, toHttpBase(settings.serverUrl), import.meta.env.BASE_URL || "/"),
);

/** Root style: character CSS variables. */
export const skinVars = computed(() => skin.value.vars);

/**
 * Member colors are made for name tags and turn muddy across a whole panel, so a theme uses a
 * livelier accent of the same hue, with gradients that lean toward neighbouring hues.
 */
const TONES: Record<string, { color: string; top: string; bottom: string }> = {
  jiaran: { color: "#F48FB1", top: "#FFD9B0", bottom: "#E8389A" },
  nailin: { color: "#4F63C9", top: "#5FD0FF", bottom: "#8A3CF0" },
  beila: { color: "#EE7F78", top: "#FFD09A", bottom: "#E8386E" },
  xinyi: { color: "#D02F7C", top: "#FF8FB0", bottom: "#8A2BE2" },
  sinuo: { color: "#7A52D6", top: "#7FB0FF", bottom: "#D63CC8" },
};

/** The brand orange of tokens.css, then one theme per member. */
export const THEME_COLORS = [
  { id: "asoul", name: "A-SOUL", color: "#FC966E", top: "#FFD7AE", bottom: "#E8386E" },
  ...manifest.characters.map(({ id, name, color }) => ({ id, name, ...(TONES[id] ?? { color: color.toUpperCase(), top: color, bottom: color }) })),
];

/** The same gradient as --grad-sky in tokens.css, for a swatch that previews the theme. */
export const themeSwatch = (t: (typeof THEME_COLORS)[number]) =>
  `linear-gradient(180deg, color-mix(in oklab, ${t.color} 84%, ${t.top}), ${t.color} 48%, color-mix(in oklab, ${t.color} 74%, ${t.bottom}))`;

/** Overrides for tokens.css. The brand palette is hand-tuned there and needs none. */
export function themeTokens(id: string): Record<string, string> {
  const theme = THEME_COLORS.find((t) => t.id === id);
  return !theme || theme === THEME_COLORS[0] ? {} : accentTokens(theme.color, theme);
}

// On :root rather than the panel: overlays and the desk widgets read the same tokens.
if (typeof document !== "undefined") {
  let applied: string[] = [];
  watch(
    () => settings.themeColor,
    (id) => {
      const root = document.documentElement.style;
      applied.forEach((name) => root.removeProperty(name));
      const tokens = themeTokens(id);
      applied = Object.keys(tokens);
      applied.forEach((name) => root.setProperty(name, tokens[name]!));
    },
    { immediate: true },
  );
}
