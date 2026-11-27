// Typed access to the generated asset manifest (scripts/build_assets.py -> src/data/manifest.json)
// plus the resolver for its two asset reference schemes:
//   bundle:<path>  shipped inside the client (public/assets/<path>)
//   pack:<path>    downloaded on demand from the room server (<server>/packs/<path>); the standalone edition ships
//                  them inside the client instead (<app>/packs/<path>, copied by standalone-packs.js)
import raw from "./data/manifest.json";
import { STANDALONE } from "./edition";

/** `limited` is the 衣橱 cards' tier: static portraits in a tier of their own, with no pity. */
export type Rarity = "common" | "uncommon" | "rare" | "limited" | "epic" | "skin" | "legendary";
export const RARITY_ORDER: Rarity[] = ["common", "uncommon", "rare", "limited", "epic", "skin", "legendary"];

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
  /** The video is one still picture over the card's sound. */
  still: boolean;
  /** The release that ships the card, for cards newer than the first ones. */
  since?: string;
  /** Set on a card with a holo version (镭射款), an item of its own: holo:<card id>. */
  holo?: ManifestHolo;
}
/** Shading of a holo version, from the official shine_effect_config (see src/holo/shader.ts). */
export interface HoloShine {
  laserIntensity: number;
  skinProtection: number;
  clothBoost: number;
  hueStart: number;
  hueRange: number;
}
/** `mask` is white where the foil goes; `since` is the release that ships the holo versions. */
export interface ManifestHolo { mask: string; shine: HoloShine; since: string }
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
export interface ManifestEmote { key: string; name: string; img: string; thumb?: string; animated?: boolean }
export interface ManifestEmoteSet {
  id: string;
  name: string;
  /** A member, or 阿草 for the scratch card set. */
  character: string;
  rarity: Rarity;
  /** Set on a set won elsewhere than resonance: never in the pool, never crafted. */
  source?: "scratch";
  /** The release that ships the set, for sets newer than the first ones: the server keeps them from older clients. */
  since?: string;
  emotes: ManifestEmote[];
}
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
/**
 * A name plate besides the big hidden cards: worn once every emote of `emoteSet`, or every card of `series`, is
 * owned. A series plate plays its own `video` (`poster` is its first frame, `still` that frame at full size;
 * `aspect` is height over width).
 */
export type ManifestPlate = { id: string; name: string } & (
  | { emoteSet: string; series?: undefined }
  | { series: string; emoteSet?: undefined; video: string; poster: string; still: string; aspect: number }
);
export type PhotoKind = "solo" | "duo" | "group";
/** A photocard (官周小卡). A solo card also comes signed, an item of its own (src/photocards.ts). */
export interface ManifestPhotocard { id: string; kind: PhotoKind; characters: string[] }
/** Photocards sold together; card ids are unique within a series. `event` is what the cards were made for. */
export interface ManifestPhotoSeries { id: string; name: string; event: string; cards: ManifestPhotocard[] }
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
  /** `name` is the id (folder, save item, room field); `title` replaces it on screen; `since` is the release that ships it. */
  skins: { name: string; member: string; title?: string; since?: string }[];
  plates: ManifestPlate[];
  photocards: ManifestPhotoSeries[];
}

export const manifest = raw as unknown as Manifest;

const cardIndex = new Map(manifest.cards.map((c) => [c.id, c]));
const emoteIndex = new Map(manifest.emoteSets.flatMap((s) => s.emotes.map((e) => [e.key, e] as const)));
const decorIndex = new Map(manifest.decor.map((d) => [d.id, d]));
const emoteSetIndex = new Map(manifest.emoteSets.flatMap((s) => s.emotes.map((e) => [e.key, s] as const)));

export const getCard = (id: string) => cardIndex.get(id);
export const getEmote = (key: string) => emoteIndex.get(key);
export const emoteCover = (key: string) => { const emote = getEmote(key); return emote?.thumb ?? emote?.img; };
export const getDecor = (id: string | null | undefined) => (id ? decorIndex.get(id) : undefined);
/** The emote set an emote key belongs to. */
export const getEmoteSet = (key: string) => emoteSetIndex.get(key);
export const getTheme = (id: string) =>
  manifest.themes.find((t) => t.id === id) ?? manifest.themes.find((t) => t.id === manifest.defaultTheme)!;
/** Member a character or skin name belongs to: 贝拉山海经 -> 贝拉. */
export const memberOf = (name: string) =>
  manifest.characters.find((c) => name.startsWith(c.name))?.name ?? name;

const skinIndex = new Map(manifest.skins.map((s) => [s.name, s]));
/** What the screen calls a character or skin: a skin's title when it has one, else its name. */
export const skinTitle = (name: string) => skinIndex.get(name)?.title ?? name;

export const characterColor = (name: string) =>
  manifest.characters.find((c) => c.name === memberOf(name))?.color ?? "#ff6b9d";

/** Resolve a `bundle:` / `pack:` reference to a URL. `serverBase` has no trailing slash. */
export function resolveAsset(ref: string | null | undefined, serverBase: string, appBase = "/"): string {
  if (!ref) return "";
  const i = ref.indexOf(":");
  const scheme = ref.slice(0, i);
  const path = ref.slice(i + 1);
  if (scheme === "bundle") return `${appBase.replace(/\/?$/, "/")}assets/${path}`;
  if (scheme === "pack" && STANDALONE) return `${appBase.replace(/\/?$/, "/")}packs/${path}`;
  // No server to ask yet (see asset.ts): nothing, rather than a path the app itself cannot serve.
  if (scheme === "pack") return serverBase ? `${serverBase.replace(/\/+$/, "")}/packs/${path}` : "";
  return ref;
}
