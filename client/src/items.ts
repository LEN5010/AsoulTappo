// Collectible items shown in the backpack, collection and craft pages.
// Ids match the server: card:<id>, emote:<key>, char:<skin name>.
// Original characters are always owned; skins use char:<name> and drop from resonance.
import { manifest, memberOf, RARITY_ORDER, type Rarity } from "./manifest";

export type ItemKind = "character" | "accessory" | "emote" | "card" | "theme" | "frame" | "badge";

export interface Item {
  /** namespaced id, e.g. "emote:jiaran-eat.03" */
  id: string;
  /** id inside its kind: character name, accessory id, emote key, card id, theme id, decor id */
  ref: string;
  kind: ItemKind;
  name: string;
  /** null for things that are not dropped (characters, starters, frames/badges) */
  rarity: Rarity | null;
  /** asset reference (bundle:/pack:); characters are drawn from their pet layers instead */
  art: string;
  characters: string[];
  /** set / series / theme name, used for grouping and details */
  group: string;
  starter: boolean;
}

export const KIND_LABEL: Record<ItemKind, string> = {
  character: "角色", accessory: "配件", emote: "表情", card: "卡牌", theme: "主题", frame: "头像框", badge: "徽章",
};
export const RARITY_LABEL = Object.fromEntries(
  RARITY_ORDER.map((r) => [r, r === "skin" ? "皮肤" : manifest.rarities[r].name]),
) as Record<Rarity, string>;
/** highest first, for grouping */
export const RARITY_DESC: Rarity[] = [...RARITY_ORDER].reverse();

const starterEmotes = new Set(manifest.starter.emotes);
const seriesName = (id: string) => manifest.series.find((s) => s.id === id)?.name ?? id;

function build(): Item[] {
  const out: Item[] = [];
  for (const c of manifest.characters) {
    out.push({ id: `char:${c.name}`, ref: c.name, kind: "character", name: c.name, rarity: null, art: "",
      characters: [c.name], group: "初始角色", starter: true });
  }
  for (const skin of manifest.skins) {
    out.push({ id: `char:${skin.name}`, ref: skin.name, kind: "character", name: skin.name,
      rarity: "skin", art: "", characters: [skin.member], group: "皮肤", starter: false });
  }
  for (const s of manifest.emoteSets) {
    for (const e of s.emotes) {
      const starter = starterEmotes.has(e.key);
      out.push({ id: `emote:${e.key}`, ref: e.key, kind: "emote", name: e.name, rarity: starter ? null : s.rarity,
        art: e.img, characters: [s.character], group: s.name, starter });
    }
  }
  for (const c of manifest.cards) {
    out.push({ id: `card:${c.id}`, ref: c.id, kind: "card", name: c.name, rarity: c.rarity, art: c.thumb,
      characters: c.characters, group: seriesName(c.series), starter: false });
  }
  return out;
}

export const items: Item[] = build();
const index = new Map(items.map((i) => [i.id, i]));
export const getItem = (id: string) => index.get(id);

/** Items available through resonance. */
export const collectible = items.filter((i) => i.rarity !== null && !i.starter);

export function ownsCharacter(name: string, owned: Record<string, number>): boolean {
  return manifest.characters.some((m) => m.name === name) || (owned[`char:${name}`] ?? 0) > 0;
}

export function ownsEmote(key: string, owned: Record<string, number>): boolean {
  return starterEmotes.has(key) || (owned[`emote:${key}`] ?? 0) > 0;
}

export function craftCost(item: Item): number | null {
  return (item.kind === "emote" || item.kind === "card") && item.rarity && !item.starter ? manifest.economy.craftCost[item.rarity] ?? null : null;
}

/** Starter emotes of one character (the default quick emotes). */
export function starterEmotesOf(character: string): string[] {
  const who = memberOf(character);
  const set = manifest.emoteSets.find((s) => s.character === who);
  return set ? set.emotes.filter((e) => starterEmotes.has(e.key)).map((e) => e.key) : [];
}

export function dropLabel(item: Item, isNew: boolean): string {
  return isNew ? `新${KIND_LABEL[item.kind]}！` : "重复获得";
}
