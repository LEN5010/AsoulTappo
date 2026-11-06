// Turns a draw's results into the tiles of the reveal board.
import { assetUrl } from "../asset";
import { cardLabel, TIER_LABEL } from "../cards";
import { getCharacter } from "../characters";
import { getItem, RARITY_LABEL, type Item } from "../items";
import { getCard, manifest, memberOf, type ManifestCard } from "../manifest";
import type { Drop } from "../net/api";
import { boardOf, DEAL_LIMIT, sealed, spotlights } from "../reveal";

export interface BoardEntry {
  key: string;
  drop: Drop & { got: number };
  item: Item;
  card?: ManifestCard;
  title: string;
  who: string;
  /** What it is once turned over: 大隐藏, 桌宠皮肤, 稀有表情. */
  kind: string;
  sealed: boolean;
  spot: boolean;
  tone: string;
  toneStyle: Record<string, string>;
  tilt: number;
  /** Tile art: the card thumbnail, the sticker, or the skin's pet artwork. */
  art: string;
}

/**
 * Member colours, hand-tuned for large bands: livelier than the name-tag colour, with a gradient that
 * leans toward neighbouring hues. `light` members take dark ink, the rest white.
 */
const MEMBER_TONES: Record<string, { color: string; top: string; bottom: string; light: boolean }> = {
  jiaran: { color: "#F48FB1", top: "#FFD9B0", bottom: "#E8389A", light: true },
  nailin: { color: "#4F63C9", top: "#5FD0FF", bottom: "#8A3CF0", light: false },
  beila: { color: "#EE7F78", top: "#FFD09A", bottom: "#E8386E", light: true },
  xinyi: { color: "#D02F7C", top: "#FF8FB0", bottom: "#8A2BE2", light: false },
  sinuo: { color: "#7A52D6", top: "#7FB0FF", bottom: "#D63CC8", light: false },
};
const rgbOf = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ");

/** A skin's tone is its member's colour, so the reveal reads as hers. */
export function memberTone(skin: string): Record<string, string> {
  const id = manifest.characters.find((c) => c.name === memberOf(skin))?.id;
  const tone = id ? MEMBER_TONES[id] : undefined;
  if (!tone) return {};
  const { color, top, bottom, light } = tone;
  return {
    "--tone-fill": `linear-gradient(180deg, color-mix(in oklab, ${color} 84%, ${top}), ${color} 48%, color-mix(in oklab, ${color} 74%, ${bottom}))`,
    "--tone-glow": `rgba(${rgbOf(color)}, 0.72)`,
    "--tone-ink": light ? "var(--ink)" : "#fff",
  };
}

// Stuck on by hand: a few degrees either way, never twice the same in a row.
const TILTS = [-3, 2.2, -1.4, 3.2, -2.4, 1.6, -2, 2.8, -1, 3.6];

export function entriesOf(drops: readonly Drop[]): BoardEntry[] {
  const grouped = drops.length > DEAL_LIMIT;
  return boardOf(drops).flatMap((drop, i) => {
    const item = getItem(drop.item);
    if (!item) return [];
    const card = item.kind === "card" ? getCard(item.ref) : undefined;
    const skin = drop.rarity === "skin";
    const label = card ? cardLabel(card) : { title: item.name, who: skin ? memberOf(item.ref) : item.characters.join(" · ") };
    const kind = skin ? "桌宠皮肤" : card && card.tier !== "normal" ? TIER_LABEL[card.tier]
      : `${RARITY_LABEL[drop.rarity]}${card ? "卡片" : "表情"}`;
    const art = card ? assetUrl(card.thumb) : skin ? getCharacter(item.ref)?.bg ?? "" : assetUrl(item.art);
    return [{
      key: `${drop.item}:${i}`,
      drop,
      item,
      card,
      title: label.title,
      who: label.who,
      kind,
      sealed: sealed(drop, grouped, card?.tier),
      spot: spotlights(drop, card?.tier),
      tone: `tone-${drop.rarity}`,
      toneStyle: skin ? memberTone(item.ref) : {},
      tilt: TILTS[i % TILTS.length]!,
      art,
    }];
  });
}
