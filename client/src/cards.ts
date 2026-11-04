// Display helpers for card pools and cards.
import { getTheme, type ManifestCard } from "./manifest";
import { accentTokens } from "./ui/palette";

export type CardTier = ManifestCard["tier"];

export const TIER_LABEL: Record<CardTier, string> = { big: "大隐藏", small: "小隐藏", normal: "普通款" };
export const TIER_RANK: Record<CardTier, number> = { big: 0, small: 1, normal: 2 };

export const byTier = (a: { tier: CardTier }, b: { tier: CardTier }) => TIER_RANK[a.tier] - TIER_RANK[b.tier];

/** Matches --accent in tokens.css. */
const BRAND_ACCENT = "#FC966E";

/** The decoration set each pool shipped with. The group-wide 绽放 pool stays on the brand palette. */
const POOL_THEME: Record<string, string> = {
  brilliant: "jiaran-album-2025",
  moon: "jiaran-album-2026",
  tavern: "nailin-tavern-2025",
  voyage: "beila-adventure-2025",
  symphony: "symphony",
};

export interface PoolSkin {
  accent: string;
  /** Accent tokens to set on the pool's subtree; empty on the brand palette. */
  tokens: Record<string, string>;
  /** Stickers for the pool stage. */
  mascots: string[];
}

export function poolSkin(seriesId: string): PoolSkin {
  const theme = getTheme(POOL_THEME[seriesId] ?? "");
  if (!POOL_THEME[seriesId] || !theme) return { accent: BRAND_ACCENT, tokens: {}, mascots: [] };
  const tokens = accentTokens(theme.colors.accent.toUpperCase());
  const { main, channel } = theme.icons;
  // The duet pool shows both of its members; the others pair the member with her prop.
  const mascots = theme.characters.length > 1 ? [main?.n, channel?.n] : [main?.n, main?.s];
  return { accent: tokens["--accent"]!, tokens, mascots: mascots.filter((m): m is string => !!m) };
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
