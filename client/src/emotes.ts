// Emote keys sent over the wire:
//   "<setId>.<nn>"  an emote from the manifest (image)   "thumbup"  the theme's like animation
// Anything else (e.g. glyph keys from old clients) is not shown.
import { getEmote, manifest, resolveAsset } from "./manifest";

export const THUMBUP = "thumbup";

export interface EmoteView {
  img?: string;
  /** Icon.vue name, drawn when there is no picture */
  icon?: string;
  /** true for the animated theme like */
  animated?: boolean;
}

export function emoteView(
  key: string,
  ctx: { serverBase: string; thumbup: string; reducedMotion: boolean; appBase?: string },
): EmoteView | null {
  if (key === THUMBUP) {
    return ctx.thumbup && !ctx.reducedMotion ? { img: ctx.thumbup, animated: true } : { icon: "thumb" };
  }
  const e = getEmote(key);
  return e ? { img: resolveAsset(e.img, ctx.serverBase, ctx.appBase) } : null;
}

/** Emote sets grouped by character, in manifest character order. */
export function emoteGroups() {
  return manifest.characters
    .map((c) => ({ character: c, sets: manifest.emoteSets.filter((s) => s.character === c.name) }))
    .filter((g) => g.sets.length > 0);
}
