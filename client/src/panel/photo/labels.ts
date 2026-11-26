// What the pages call a photocard.
import type { PhotoItem, PhotoItemKind } from "../../photocards";

export const PHOTO_KINDS: readonly PhotoItemKind[] = ["solo", "duo", "group", "sign"];
export const PHOTO_KIND_LABEL: Record<PhotoItemKind, string> = { solo: "单人", duo: "双人", group: "团体", sign: "签名" };

/** The card's number within those of the same members. */
export const photoNo = (item: PhotoItem) => (/\d+$/.exec(item.card)?.[0] ?? "").padStart(2, "0");
/** Who is on it. */
export const photoWho = (item: PhotoItem) =>
  (item.kind === "group" ? "A-SOUL" : item.characters.join(" × "));
export const photoName = (item: PhotoItem) =>
  `${photoWho(item)} ${photoNo(item)}${item.kind === "sign" ? " 签名" : ""}`;

export type PhotoFilter = "all" | PhotoItemKind | "owned" | "missing";
export const PHOTO_FILTERS: { id: PhotoFilter; label: string }[] = [
  { id: "all", label: "全部" }, ...PHOTO_KINDS.map((id) => ({ id, label: PHOTO_KIND_LABEL[id] })),
  { id: "owned", label: "已拥有" }, { id: "missing", label: "未拥有" },
];
export const filterPhotos = (items: readonly PhotoItem[], filter: PhotoFilter, owned: ReadonlySet<string>): PhotoItem[] =>
  items.filter((i) => filter === "all" || (filter === "owned" || filter === "missing"
    ? owned.has(i.id) === (filter === "owned") : i.kind === filter));

export interface AlbumSection { key: string; label: string; member: string; wide: boolean; items: PhotoItem[] }
/** The album's shelves: one a member, her cards and then the signed ones; then the duos, then the group. */
export function albumSections(items: readonly PhotoItem[]): AlbumSection[] {
  const out = new Map<string, AlbumSection>();
  for (const item of items) {
    const wide = item.kind === "duo" || item.kind === "group";
    const member = wide ? "" : item.characters[0] ?? "";
    const key = wide ? item.kind : member;
    let s = out.get(key);
    if (!s) out.set(key, s = { key, label: wide ? PHOTO_KIND_LABEL[item.kind] : member, member, wide, items: [] });
    s.items.push(item);
  }
  const rank = (s: AlbumSection) => (s.key === "group" ? 2 : s.wide ? 1 : 0);
  return [...out.values()].sort((a, b) => rank(a) - rank(b));
}
