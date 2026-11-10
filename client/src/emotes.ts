// Emote keys sent over the wire:
//   "<setId>.<nn>"  an emote from the manifest (image)
import { getEmote, resolveAsset } from "./manifest";

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
