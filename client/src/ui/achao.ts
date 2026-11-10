// 阿草, the alpaca: its stickers by name. They are the emotes of the scratch card set, bundled with the client.
import { manifest, resolveAsset } from "../manifest";

const emotes = manifest.emoteSets.find((s) => s.id === manifest.economy.scratch.emote.set)?.emotes ?? [];

export const ACHAO: Record<string, string> = Object.fromEntries(
  emotes.map((e) => [e.name, resolveAsset(e.img, "", import.meta.env.BASE_URL || "/")]),
);
