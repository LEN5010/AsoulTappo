import { computed, ref } from "vue";
import { toHttpBase } from "../net/protocol";
import { buildSkin, cssImage } from "../skin";
import { settings } from "./settings";

export const reducedMotion = ref(false);
if (typeof window !== "undefined" && window.matchMedia) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  reducedMotion.value = mq.matches;
  mq.addEventListener?.("change", (e) => (reducedMotion.value = e.matches));
}

export const skin = computed(() =>
  buildSkin(settings.theme, settings.character, toHttpBase(settings.serverUrl), import.meta.env.BASE_URL || "/"),
);

/** Root style: theme/character CSS variables. */
export const skinVars = computed(() => skin.value.vars);

export { cssImage };
