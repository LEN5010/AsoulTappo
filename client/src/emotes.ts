// Emote keys sent over the wire:
//   "<setId>.<nn>"  an emote from the manifest (image)
import { getEmote, manifest, resolveAsset } from "./manifest";

export interface EmoteView {
  img: string;
}

export function emoteView(
  key: string,
  ctx: { serverBase: string; appBase?: string },
): EmoteView | null {
  const e = getEmote(key);
  return e ? { img: resolveAsset(e.img, ctx.serverBase, ctx.appBase) } : null;
}

/** Emote sets grouped by character, in manifest character order. */
export function emoteGroups() {
  return manifest.characters
    .map((c) => ({ character: c, sets: manifest.emoteSets.filter((s) => s.character === c.name) }))
    .filter((g) => g.sets.length > 0);
}
