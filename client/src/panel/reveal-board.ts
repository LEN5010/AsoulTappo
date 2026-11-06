// Turns a draw's results into the tiles of the reveal board.
import { assetUrl } from "../asset";
import { cardLabel, TIER_LABEL } from "../cards";
import { getCharacter } from "../characters";
import { getItem, RARITY_LABEL, type Item } from "../items";
import { getCard, manifest, memberOf, type ManifestCard, type Rarity } from "../manifest";
import type { Drop } from "../net/api";
import { boardOf, DEAL_LIMIT, sealed, spotlights } from "../reveal";
import { THEME_COLORS, themeSwatch } from "../stores/theme";
import { accentTokens } from "../ui/palette";

export interface BoardEntry {
  key: string;
  drop: Drop & { got: number };
  item: Item;
  card?: ManifestCard;
  title: string;
  who: string;
  /** What it is once turned over: 大隐藏, 桌宠皮肤, 稀有表情. */
  kind: string;
  /** What a face-down tile admits to: its rarity, which its colour already gives away. */
  hint: string;
  sealed: boolean;
  spot: boolean;
  tone: string;
  toneStyle: Record<string, string>;
  tilt: number;
  /** Tile art: the card thumbnail, the sticker, or the skin's pet artwork. */
  art: string;
}

/** A skin's tone is its member's theme, so it reads as hers whichever theme is on. */
export function memberTone(skin: string): Record<string, string> {
  const id = manifest.characters.find((c) => c.name === memberOf(skin))?.id;
  const theme = THEME_COLORS.find((t) => t.id === id);
  if (!theme) return {};
  const tokens = accentTokens(theme.color, theme);
  return {
    "--tone-fill": themeSwatch(theme),
    "--tone-glow": `rgba(${tokens["--accent-rgb"]}, 0.72)`,
    "--tone-ink": tokens["--on-accent"]!,
  };
}

// Stuck on by hand: a few degrees either way, never twice the same in a row.
const TILTS = [-3, 2.2, -1.4, 3.2, -2.4, 1.6, -2, 2.8, -1, 3.6];
const HINT: Partial<Record<Rarity, string>> = { legendary: "大隐藏", skin: "皮肤" };

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
      hint: HINT[drop.rarity] ?? RARITY_LABEL[drop.rarity],
      sealed: sealed(drop, grouped, card?.tier),
      spot: spotlights(drop, card?.tier),
      tone: `tone-${drop.rarity}`,
      toneStyle: skin ? memberTone(item.ref) : {},
      tilt: TILTS[i % TILTS.length]!,
      art,
    }];
  });
}
