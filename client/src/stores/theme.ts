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

/** The brand orange of tokens.css, then one support color per member. */
export const THEME_COLORS = [
  { id: "asoul", name: "A-SOUL", color: "#FC966E" },
  ...manifest.characters.map(({ id, name, color }) => ({ id, name, color: color.toUpperCase() })),
];

/** Overrides for tokens.css. The brand palette is hand-tuned there and needs none. */
export function themeTokens(id: string): Record<string, string> {
  const theme = THEME_COLORS.find((t) => t.id === id);
  return !theme || theme === THEME_COLORS[0] ? {} : accentTokens(theme.color);
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
