// Photocards (官周小卡): the cards of the manifest's series, what an item id names, and the odds of a box. No storage and
// no requests: the save's own cards and boxes are in stores/photocards.ts, the rules in server/app/photo_deal.py.
// Item ids match the server: photo:<series>/<card>, and sign:<series>/<card> for a solo card's signed version. They are
// apart from the items of src/items.ts: they count in no album, total or board.
import { manifest, type ManifestPhotoSeries, type PhotoKind } from "./manifest";
import type { PhotocardConfig } from "./stores/economy";

export type PhotoRareKind = "duo" | "group" | "sign";
export type PhotoItemKind = PhotoKind | "sign";
export interface PhotoItem {
  id: string;
  series: string;
  /** The card's id in its series; a signed card's is that of its solo card. */
  card: string;
  kind: PhotoItemKind;
  characters: string[];
}

export const PHOTO_RARE_KINDS: readonly PhotoRareKind[] = ["duo", "group", "sign"];
const KIND_ORDER: readonly PhotoItemKind[] = ["solo", ...PHOTO_RARE_KINDS];

function itemsOf(series: string): PhotoItem[] {
  const cards = manifest.photocards.find((s) => s.id === series)?.cards ?? [];
  const items: PhotoItem[] = cards.map((c) => ({
    id: `photo:${series}/${c.id}`, series, card: c.id, kind: c.kind, characters: c.characters,
  }));
  for (const c of cards.filter((c) => c.kind === "solo")) {
    items.push({ id: `sign:${series}/${c.id}`, series, card: c.id, kind: "sign", characters: c.characters });
  }
  return items.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}

/** The series this build has the cards of, in manifest order, with their names. */
export const photoSeries: readonly ManifestPhotoSeries[] = manifest.photocards;
const bySeries = new Map(photoSeries.map((s) => [s.id, itemsOf(s.id)]));
const index = new Map([...bySeries.values()].flat().map((i) => [i.id, i]));

/** Every item of a series: solo, duo, group and signed cards, each in manifest order. None of one this build lacks. */
export const photoItems = (series: string): readonly PhotoItem[] => bySeries.get(series) ?? [];
export const photoItem = (id: string): PhotoItem | undefined => index.get(id);
export const photoItemsOf = (series: string, kind: PhotoItemKind): PhotoItem[] =>
  photoItems(series).filter((i) => i.kind === kind);
export const isRarePhoto = (item: PhotoItem): boolean => item.kind !== "solo";
/** Cards that lie on their side. */
export const isWidePhoto = (item: PhotoItem): boolean => item.kind === "duo" || item.kind === "group";

/** The signed version of a solo card, or the solo card of a signed one; undefined for the others. */
export function photoPair(item: PhotoItem): PhotoItem | undefined {
  if (item.kind === "solo") return index.get(`sign:${item.series}/${item.card}`);
  return item.kind === "sign" ? index.get(`photo:${item.series}/${item.card}`) : undefined;
}

/** Percent of cards that are each rare kind, and any of them, the certain card of a box included and the signed-card
 *  pity not. */
export function photoOdds(cfg: PhotocardConfig): Record<PhotoRareKind | "rare", number> {
  const rare = cfg.sure !== false ? (100 + (cfg.size - 1) * cfg.rare) / cfg.size : cfg.rare;
  const total = PHOTO_RARE_KINDS.reduce((sum, k) => sum + cfg.split[k], 0);
  const of = (k: PhotoRareKind) => (total ? (rare * cfg.split[k]) / total : 0);
  return { rare, duo: of("duo"), group: of("group"), sign: of("sign") };
}

/** [items], all of one kind that [rate] percent of cards are, in sets of those that weigh the same (economy `weight`),
 *  each with the percent of cards it gives while the save holds none of them: the set of the most first. */
export function photoShares(
  cfg: PhotocardConfig, items: readonly PhotoItem[], rate: number,
): { items: PhotoItem[]; rate: number }[] {
  const weigh = (i: PhotoItem) => (i.kind === "sign" ? 1 : cfg.weight?.[i.card] ?? 1);
  const total = items.reduce((sum, i) => sum + weigh(i), 0);
  const sets = new Map<number, PhotoItem[]>();
  for (const i of items) sets.set(weigh(i), [...(sets.get(weigh(i)) ?? []), i]);
  return [...sets].sort(([, a], [, b]) => b.length - a.length)
    .map(([w, list]) => ({ items: list, rate: total ? (rate * w * list.length) / total : 0 }));
}
