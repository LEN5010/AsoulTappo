// Emote keys sent over the wire:
//   "<setId>.<nn>"  an emote from the manifest (image)   "thumbup"  the theme's like animation
//   legacy glyph keys (heart, clap, ...) are still understood; unknown keys are shown as text.
import { getEmote, manifest, resolveAsset } from "./manifest";

export const THUMBUP = "thumbup";

export const EMOTES: { key: string; glyph: string; label: string }[] = [
  { key: "heart", glyph: "❤️", label: "爱心" },
  { key: "clap", glyph: "👏", label: "鼓掌" },
  { key: "laugh", glyph: "😂", label: "笑哭" },
  { key: "party", glyph: "🎉", label: "庆祝" },
  { key: "cry", glyph: "😭", label: "大哭" },
  { key: "fire", glyph: "🔥", label: "火" },
  { key: "star", glyph: "⭐", label: "星星" },
  { key: "bread", glyph: "🍞", label: "小面包" },
];

export function emoteGlyph(key: string): string {
  return EMOTES.find((e) => e.key === key)?.glyph ?? key.slice(0, 4);
}

export interface EmoteView {
  img?: string;
  text?: string;
  /** true for the animated theme like */
  animated?: boolean;
}

export function emoteView(
  key: string,
  ctx: { serverBase: string; thumbup: string; reducedMotion: boolean; appBase?: string },
): EmoteView {
  if (key === THUMBUP) {
    return ctx.thumbup && !ctx.reducedMotion ? { img: ctx.thumbup, animated: true } : { text: "👍" };
  }
  const e = getEmote(key);
  if (e) return { img: resolveAsset(e.img, ctx.serverBase, ctx.appBase) };
  return { text: emoteGlyph(key) };
}

/** Emote sets grouped by character, in manifest character order. */
export function emoteGroups() {
  return manifest.characters
    .map((c) => ({ character: c, sets: manifest.emoteSets.filter((s) => s.character === c.name) }))
    .filter((g) => g.sets.length > 0);
}
