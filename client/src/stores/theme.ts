import { computed, ref } from "vue";
import { toHttpBase } from "../net/protocol";
import { buildSkin } from "../skin";
import { settings } from "./settings";

/**
 * Always false: the system's reduce-motion setting is not followed, so the curtain, the card flips and the shard
 * flights play everywhere (Windows sets it whenever its animation effects are off). The calm branches that read it
 * stay in place for now.
 */
export const reducedMotion = ref(false);

export const skin = computed(() =>
  buildSkin("jiaran-eat", settings.character, toHttpBase(settings.serverUrl), import.meta.env.BASE_URL || "/"),
);

/** Root style: character CSS variables. */
export const skinVars = computed(() => skin.value.vars);
