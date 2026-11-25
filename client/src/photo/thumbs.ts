// Small pictures of the photocards (scripts/photocards/thumbs.py), for the pages: the shop's strip and rows, the album.
// A signed card is its solo card's picture with the signature laid over it.
import type { PhotoItem } from "../photocards";

interface Sheet {
  templates: Record<string, { size: [number, number]; back: string }>;
  signs: Record<string, { box: [number, number, number, number] }>;
}
const pictures = import.meta.glob<string>("../assets/photocards/*/thumb/*.webp",
  { eager: true, query: "?url", import: "default" });
const sheets = import.meta.glob<Sheet>("../assets/photocards/*/cards.json", { eager: true, import: "default" });

const at = (series: string, name: string) => pictures[`../assets/photocards/${series}/thumb/${name}.webp`];
const template = (item: PhotoItem) =>
  sheets[`../assets/photocards/${item.series}/cards.json`]?.templates[item.card.replace(/-\d+$/, "")];

/** The card's small picture; undefined in a build without its art. */
export const photoThumb = (item: PhotoItem): string | undefined => at(item.series, item.card);

/** The signature over a signed card's picture and where it lies on it, as CSS lengths. */
export function photoInk(item: PhotoItem): { src: string; style: Record<string, string> } | null {
  const card = item.kind === "sign" ? template(item) : undefined;
  const sign = card && sheets[`../assets/photocards/${item.series}/cards.json`]?.signs[card.back];
  const src = card && at(item.series, `sign-${card.back}`);
  if (!card || !sign || !src) return null;
  const [w, h] = card.size;
  const [x, y, sw, sh] = sign.box;
  const part = (v: number, of: number) => `${(v / of) * 100}%`;
  return { src, style: { left: part(x, w), top: part(y, h), width: part(sw, w), height: part(sh, h) } };
}
