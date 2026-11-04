// Typed access to the generated asset manifest (scripts/build_assets.py -> src/data/manifest.json)
// plus the resolver for its two asset reference schemes:
//   bundle:<path>  shipped inside the client (public/assets/<path>)
//   pack:<path>    downloaded on demand from the room server (<server>/packs/<path>)
import raw from "./data/manifest.json";

export type Rarity = "common" | "uncommon" | "rare" | "epic" | "skin" | "legendary";
export const RARITY_ORDER: Rarity[] = ["common", "uncommon", "rare", "epic", "skin", "legendary"];

export interface ManifestCharacter { id: string; name: string; color: string }
export interface ManifestCard {
  id: string;
  name: string;
  series: string;
  sub: string | null;
  characters: string[];
  rarity: Rarity;
  tier: "big" | "small" | "normal";
  thumb: string;
  full: string;
  video: string | null;
}
export interface ThemeIcon { n: string; s: string }
export interface ManifestTheme {
  id: string;
  name: string;
  characters: string[];
  default: boolean;
  pack: string | null;
  cover: string;
  preview: string | null;
  /** null for the default (starter) theme */
  rarity: Rarity | null;
  colors: { accent: string; tint: string; headFg?: string; tabFg?: string };
  icons: Record<string, ThemeIcon>;
  parts: {
    headBg?: string;
    tabBg?: string;
    banner?: string;
    backgrounds?: string[];
    thumbup?: string;
    loading?: string;
  };
}
export interface ManifestEmote { key: string; name: string; img: string }
export interface ManifestEmoteSet { id: string; name: string; character: string; rarity: Rarity; emotes: ManifestEmote[] }
export interface ManifestAccessory {
  id: string;
  name: string;
  /** figure: static; anim: animated loop */
  kind: "figure" | "anim";
  slot: "head" | "desk";
  characters: string[];
  rarity: Rarity;
  img: string;
}
export interface ManifestDecor {
  id: string;
  kind: "frame" | "badge";
  name: string;
  img: string;
  unlock: { series: string; min: number };
}
export interface ManifestSeries { id: string; name: string; total: number }
export interface Manifest {
  version: number;
  characters: ManifestCharacter[];
  rarities: Record<Exclude<Rarity, "skin">, { name: string }>;
  defaultTheme: string;
  themes: ManifestTheme[];
  series: ManifestSeries[];
  cards: ManifestCard[];
  emoteSets: ManifestEmoteSet[];
  decor: ManifestDecor[];
  accessories: ManifestAccessory[];
  starter: { emotes: string[]; theme: string };
  skins: { name: string; member: string }[];
  economy: {
    income: { perMinute: number; maxMultiplier: number; fullTapsPerMinute: number };
    resonance: { cost: number; rates: Record<Rarity, number>; pity: { legendary: number; skin: number }; commonKindWeights: { card: number; emote: number }; duplicateRefund: number };
    craftCost: Partial<Record<Rarity, number>>;
  };
}

export const manifest = raw as unknown as Manifest;

const cardIndex = new Map(manifest.cards.map((c) => [c.id, c]));
const emoteIndex = new Map(manifest.emoteSets.flatMap((s) => s.emotes.map((e) => [e.key, e] as const)));
const decorIndex = new Map(manifest.decor.map((d) => [d.id, d]));
const accessoryIndex = new Map(manifest.accessories.map((a) => [a.id, a]));
const emoteSetIndex = new Map(manifest.emoteSets.flatMap((s) => s.emotes.map((e) => [e.key, s] as const)));

export const getCard = (id: string) => cardIndex.get(id);
export const getEmote = (key: string) => emoteIndex.get(key);
export const getDecor = (id: string | null | undefined) => (id ? decorIndex.get(id) : undefined);
export const getAccessory = (id: string | null | undefined) => (id ? accessoryIndex.get(id) : undefined);
/** The emote set an emote key belongs to. */
export const getEmoteSet = (key: string) => emoteSetIndex.get(key);
export const getTheme = (id: string) =>
  manifest.themes.find((t) => t.id === id) ?? manifest.themes.find((t) => t.id === manifest.defaultTheme)!;
/** Member a character or skin name belongs to: 贝拉山海经 -> 贝拉. */
export const memberOf = (name: string) =>
  manifest.characters.find((c) => name.startsWith(c.name))?.name ?? name;

export const characterColor = (name: string) =>
  manifest.characters.find((c) => c.name === memberOf(name))?.color ?? "#ff6b9d";

/** Resolve a `bundle:` / `pack:` reference to a URL. `serverBase` has no trailing slash. */
export function resolveAsset(ref: string | null | undefined, serverBase: string, appBase = "/"): string {
  if (!ref) return "";
  const i = ref.indexOf(":");
  const scheme = ref.slice(0, i);
  const path = ref.slice(i + 1);
  if (scheme === "bundle") return `${appBase.replace(/\/?$/, "/")}assets/${path}`;
  if (scheme === "pack") return `${serverBase.replace(/\/+$/, "")}/packs/${path}`;
  return ref;
}
