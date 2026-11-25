// What the photocards of a series look like: the pictures and finishes of every card, its colours, the members'
// signatures. The list of cards is the manifest's; templates, places and signatures are the series' cards.json
// (scripts/photocards). Nothing here draws.
import { manifest, type PhotoKind } from "../manifest";
import type { Vec2, Vec3, Vec4 } from "./gl";

interface Tint { dark: Vec3; lit: Vec3 }
/** What the cards of a member, a pair or the group have in common. */
interface Template {
  /** In texels; the short side is 1080. */
  size: Vec2;
  /** The name of its back: several templates share one. */
  back: string;
  /** The front's deep foil, and the back's lettering. */
  foil: Tint;
  print: Tint;
}
/** The stage of a series' key visual. Places are parts of the picture, colours 0 to 1. */
export interface StageLook {
  /** What it is shaded with. */
  dark: Vec3;
  /** What it whitens through on its way into the page's paper: its own light, so no other colour comes between. */
  mist: Vec3;
  /** The ground it stands on, from top to bottom. */
  ground: readonly [Vec3, Vec3];
  /** The colour of its light, and where its lamps are. */
  light: Vec3;
  lamps: readonly Vec2[];
}
/** What a series looks like as a whole. */
export interface SeriesLook {
  /** The colour of its box's board, and of the same board where it is rubbed. */
  box: Vec3;
  rub: Vec3;
  /** The light behind it on the page, as CSS has it. */
  wash: string;
  /** Set for a series with a key visual. */
  stage?: StageLook;
}
interface Sheet {
  look: SeriesLook;
  templates: Record<string, Template>;
  /** Who stands where on a card of several, from left to right. */
  stand: Record<string, string[]>;
  /** By member: its place on the card in texels, the milliseconds it takes to write, the pen's path. */
  signs: Record<string, { box: Vec4; ms: number; tip: Vec2[] }>;
}

/** A side of a card: what is printed on it, and its finishes. */
export type SideArt = readonly [base: string, mat: string];
export interface SignArt {
  member: string;
  url: string;
  /** Its place on the card in texels: left, top, width, height. */
  box: Vec4;
  /** The same, as parts of the card. */
  uv: Vec4;
  /** How long it takes to write. */
  ms: number;
  /** Where the pen is, in texels, at even steps of that time. */
  tip: readonly Vec2[];
}
export interface CardInfo extends Template {
  series: string;
  id: string;
  kind: PhotoKind;
  characters: readonly string[];
  /** Who is on it, from left to right. */
  stand: readonly string[];
  /** It lies on its side. */
  land: boolean;
  /** The colours lie the way the members stand. */
  tones: readonly Vec3[];
  /** The colours of the light its bag holds. */
  light: readonly Vec3[];
  front: SideArt;
  behind: SideArt;
  /** Set on a signed card. */
  signed?: SignArt;
}
/** A series' key visual (scripts/photocards/stage.py): the page stands on it. */
export interface StageArt {
  id: string;
  look: StageLook;
  /** The key visual from sharp to the blur it has behind the box. */
  focus: readonly string[];
  /** How near everything in it is. */
  depth: string;
  /** The event's title. */
  title: string;
}
export interface SeriesArt {
  id: string;
  look: SeriesLook;
  /** null for a series without a key visual: its page is paper. */
  stage: StageArt | null;
  /** What is printed on its box. */
  boxInk: string;
  /** In the manifest's order. */
  cards: readonly CardInfo[];
  signs: Readonly<Record<string, SignArt>>;
  card(id: string): CardInfo | undefined;
  /** The signed version of a solo card. */
  signed(id: string): CardInfo | undefined;
}

const files = import.meta.glob<string>("../assets/photocards/*/{front,back,mat,sign,thumb,shop}/*.webp",
  { eager: true, query: "?url", import: "default" });
const inks = import.meta.glob<string>("../assets/photocards/*/box.webp",
  { eager: true, query: "?url", import: "default" });
const sheets = import.meta.glob<Sheet>("../assets/photocards/*/cards.json", { eager: true, import: "default" });
const stages = import.meta.glob<string>("../assets/photocards/*/{stage/*,title}.webp",
  { eager: true, query: "?url", import: "default" });
const opening = import.meta.glob<string>("../assets/photocards/open/*.webp",
  { eager: true, query: "?url", import: "default" });

/** The pictures every series shares: the room foil mirrors, a soft shadow. */
export const OPEN_ART = {
  room: opening["../assets/photocards/open/room.webp"],
  shadow: opening["../assets/photocards/open/shadow.webp"],
};

const fileOf = (id: string, path: string): string | undefined => files[`../assets/photocards/${id}/${path}.webp`];
/** The shelf as it stands, and the box alone (scripts/photocards/poster.cjs). */
export const seriesPoster = (id: string): string | undefined => fileOf(id, "shop/poster");
export const seriesMini = (id: string): string | undefined => fileOf(id, "shop/mini");
/** A card's small picture, for the spread. */
export const cardThumb = (info: { series: string; id: string }): string | undefined => fileOf(info.series, `thumb/${info.id}`);

/** Members, as the art names them. */
const MEMBERS: Record<string, string> = { 嘉然: "diana", 贝拉: "bella", 乃琳: "eileen" };
const TONES: Record<string, Vec3> = {
  diana: [0.98, 0.66, 0.77], bella: [0.98, 0.58, 0.52], eileen: [0.55, 0.68, 0.98],
};
const GOLD_TONE: Vec3 = [1.0, 0.84, 0.5];
// As light the colours are deeper, or over silver they would all be nearly white. A signed card's is gold alone.
const deep = (t: Vec3): Vec3 => {
  const most = Math.max(...t);
  return [(t[0] / most) ** 1.8, (t[1] / most) ** 1.8, (t[2] / most) ** 1.8];
};
/** What the stage's lamps do for a kind of card: the members' colours from left to right as they stand there, one lamp
 *  at a time, two, or all; gold for the signed. */
export function memberLight(kind: PhotoKind | "sign"): { tones: readonly Vec3[]; turns: 1 | 2 | 3 } {
  if (kind === "sign") return { tones: [deep(GOLD_TONE)], turns: 3 };
  return { tones: [TONES.bella, TONES.eileen, TONES.diana].map(deep), turns: kind === "solo" ? 1 : kind === "duo" ? 2 : 3 };
}
const templateOf = (card: string) => card.replace(/-\d+$/, "");

function stageOf(id: string, look: StageLook | undefined): StageArt | null {
  const url = (path: string): string | undefined => stages[`../assets/photocards/${id}/${path}.webp`];
  const focus: string[] = [];
  for (let i = 0, f = url("stage/0"); f; f = url(`stage/${++i}`)) focus.push(f);
  const depth = url("stage/depth"), title = url("title");
  return look && focus.length > 1 && depth && title ? { id, look, focus, depth, title } : null;
}

function build(id: string): SeriesArt | null {
  const list = manifest.photocards.find((s) => s.id === id)?.cards;
  const sheet = sheets[`../assets/photocards/${id}/cards.json`];
  if (!list || !sheet) return null;
  const url = (path: string) => fileOf(id, path)!;
  const signs: Record<string, SignArt> = {};
  for (const [member, s] of Object.entries(sheet.signs)) {
    const uv: Vec4 = [s.box[0] / 1080, s.box[1] / 1720, s.box[2] / 1080, s.box[3] / 1720];
    signs[member] = { member, url: url(`sign/${member}`), box: s.box, uv, ms: s.ms, tip: s.tip };
  }
  const cards: CardInfo[] = [];
  for (const { id: card, kind, characters } of list) {
    const name = templateOf(card), t = sheet.templates[name];
    if (!t) continue;
    const stand = sheet.stand[card] ?? characters.map((c) => MEMBERS[c]);
    const tones = stand.map((k) => TONES[k]);
    cards.push({
      series: id, id: card, kind, characters, stand, ...t, land: t.size[0] > t.size[1], tones, light: tones.map(deep),
      front: [url(`front/${card}`), url(`mat/front-${name}`)],
      behind: [url(`back/${t.back}`), url(`mat/back-${t.back}`)],
    });
  }
  const signedCards = cards.filter((c) => c.kind === "solo" && signs[c.back]).map((c): CardInfo => (
    { ...c, signed: signs[c.back], tones: [GOLD_TONE, ...c.tones], light: [deep(GOLD_TONE)] }));
  const plain = new Map(cards.map((c) => [c.id, c])), signed = new Map(signedCards.map((c) => [c.id, c]));
  return {
    id, look: sheet.look, stage: stageOf(id, sheet.look.stage), boxInk: inks[`../assets/photocards/${id}/box.webp`]!, cards, signs,
    card: (card) => plain.get(card), signed: (card) => signed.get(card),
  };
}

const built = new Map<string, SeriesArt | null>();
/** A series' art; null in a build that lacks it. */
export function seriesArt(id: string): SeriesArt | null {
  let art = built.get(id);
  if (art === undefined) built.set(id, art = build(id));
  return art;
}
