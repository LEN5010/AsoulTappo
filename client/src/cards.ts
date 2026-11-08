// Display helpers for card pools and cards.
import type { ManifestCard } from "./manifest";

export type CardTier = ManifestCard["tier"];

export const TIER_LABEL: Record<CardTier, string> = { big: "大隐藏", small: "小隐藏", normal: "普通款" };
export const TIER_RANK: Record<CardTier, number> = { big: 0, small: 1, normal: 2 };

/** The metal frame a card wears: gold for big hidden cards, coral for small hidden and dance cards, none for the rest. */
export function cardFrame(card: Pick<ManifestCard, "tier" | "rarity"> | undefined): "frame-gold" | "frame-rose" | "" {
  if (!card) return "";
  if (card.tier === "big") return "frame-gold";
  return card.tier === "small" || card.rarity === "epic" ? "frame-rose" : "";
}

/** The word stamped on a card in the reveal and on the resonance page: VOICE when its video is a still picture
 *  over its sound, DANCE when it moves. */
export function cardWord(card: Pick<ManifestCard, "tier" | "video" | "still">): string {
  if (card.tier === "big") return "SECRET";
  if (card.tier === "small") return "HIDDEN";
  if (!card.video) return "NEW";
  return card.still ? "VOICE" : "DANCE";
}

export const byTier = (a: { tier: CardTier }, b: { tier: CardTier }) => TIER_RANK[a.tier] - TIER_RANK[b.tier];

export function playsCardVideo(card: Pick<ManifestCard, "video">, owned: number | undefined, reducedMotion: boolean, preview = false): boolean {
  return !!card.video && (preview || !!owned) && !reducedMotion;
}

/** Short pool name for tabs: 嘉然的画册 · 绚烂心迹 -> 绚烂心迹, A-SOUL 绽放收藏集 -> 绽放. */
export function poolName(name: string): string {
  const bare = name.replace(/^A-SOUL\s*[·\s]\s*/, "").replace(/收藏集$/, "").trim() || name;
  return bare.split(" · ").at(-1)!.trim();
}

/** Two lines for a card tile: 时序系列-嘉然 -> 时序系列 / 嘉然. Other names keep their members as the second line. */
export function cardLabel(card: Pick<ManifestCard, "name" | "characters">): { title: string; who: string } {
  const at = card.name.lastIndexOf("-");
  const tail = at > 0 ? card.name.slice(at + 1) : "";
  if (tail && card.characters.includes(tail)) return { title: card.name.slice(0, at), who: tail };
  return { title: card.name.replace(/^《(.+)》$/, "$1"), who: card.characters.join(" · ") };
}
