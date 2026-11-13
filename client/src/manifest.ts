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
  /** The video is one still picture over the card's sound. */
  still: boolean;
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
export interface ManifestEmote { key: string; name: string; img: string; thumb?: string; animated?: boolean }
export interface ManifestEmoteSet {
  id: string;
  name: string;
  /** A member, or 阿草 for the scratch card set. */
  character: string;
  rarity: Rarity;
  /** Set on a set won elsewhere than resonance: never in the pool, never crafted. */
  source?: "scratch";
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
/** A name plate besides the big hidden cards: worn once every emote of `emoteSet` is owned. */
export interface ManifestPlate { id: string; name: string; emoteSet: string }
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
  economy: {
    /** Shards per day: dailyCap × (1 − e^−x), x = a·m + b·m² + c·m³ for m thousand taps and curve = [a, b, c];
     * a minute counts tapsPerMinute taps at most. */
    income: { dailyCap: number; curve: [number, number, number]; tapsPerMinute: number };
    resonance: {
      cost: number; rates: Record<Rarity, number>; pity: { legendary: number; skin: number }; commonKindWeights: { card: number; emote: number };
      /** Shards a repeat turns into: every emote, and cards by tier. */
      duplicateRefund: Partial<Record<"emote" | "big" | "small" | "normal", number>>;
      /** Tiers that keep their odds once complete, rolling repeats. */
      repeatTiers?: Rarity[];
    };
    craftCost: Partial<Record<Rarity, number>>;
    /** Daily check-in prizes, smallest first; weights are percentages. A prize pays its shards give or take `spread`. */
    checkin: { prizes: { shards: number; weight: number }[]; spread: number };
    /**
     * Scratch cards: `price` shards each, `daily` a China day. Weights are percentages; the rest of 100 wins nothing.
     * The emote tier gives a missing emote of `set`, for certain on the `pity`-th card since the last one. Once the
     * set is whole the tier and its pity are gone and its weight wins nothing. The room is told about `announce`
     * shards or more.
     */
    scratch: {
      price: number;
      daily: number;
      prizes: { shards: number; weight: number }[];
      emote: { set: string; weight: number; pity: number };
      announce: number;
    };
    /**
     * Rock-paper-scissors in rooms: both pay `bet`, the winner gets `prize`. An invite waits `inviteSec`, a round
     * `throwSec`. A save's net win of a China day stays at or below `dailyWinCap`; both saves need `minTaps` taps in
     * all.
     */
    duel?: {
      stakes: { bet: number; prize: number }[];
      inviteSec: number;
      throwSec: number;
      dailyWinCap: number;
      minTaps: number;
    };
    /** The park (scripts/asset_catalog.py PARK explains every field). Missing on servers without one. */
    park?: {
      /**
       * Coins: `price` shards each, at most `dailyBuy` bought a China day and none while `hold` are held, `gift`
       * free a day. Buying and the gift need `minTaps` taps in all. Every `stampsPerCoin` stamps make a coin;
       * `badges` are the stamp totals of the three badges.
       */
      coin: { price: number; dailyBuy: number; hold: number; gift: number; minTaps: number; stampsPerCoin: number; badges: number[] };
      /** Coin scratch cards (park_scratch.py): weights are percentages, the rest of 100 misses. */
      scratch?: {
        cards: Record<"basic" | "premium", {
          coins: number; again: number; prizes: { shards: number; weight: number }[];
          emote?: { set: string; weight: number; pity: number }; skin?: { weight: number; shards: number }; big?: { weight: number; shards: number };
        }>;
        jackpot: { perCoin: number; seed: number; odds: number };
        roomAt: Record<"basic" | "premium", number>;
        serverAt: Record<"basic" | "premium", number>;
      };
      race?: import("./panel/park/race").RaceConfig;
      lottery?: { daily: number; closeAt: number; drawAt: number; top: number; topCap: number; second: number; third: number };
    };
  };
  plates: ManifestPlate[];
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
  // No server to ask yet (see asset.ts): nothing, rather than a path the app itself cannot serve.
  if (scheme === "pack") return serverBase ? `${serverBase.replace(/\/+$/, "")}/packs/${path}` : "";
  return ref;
}
