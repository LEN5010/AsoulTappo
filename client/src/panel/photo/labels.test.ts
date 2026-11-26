import { describe, expect, it } from "vitest";
import { photoItems } from "../../photocards";
import { albumSections, filterPhotos, photoName, photoNo } from "./labels";

const items = photoItems("asoul2026");
const find = (id: string) => items.find((i) => i.id === id)!;

describe("photocard labels", () => {
  it("names a card by who is on it and its number", () => {
    expect(photoName(find("photo:asoul2026/diana-3"))).toBe("嘉然 03");
    expect(photoName(find("sign:asoul2026/diana-3"))).toBe("嘉然 03 签名");
    expect(photoName(find("photo:asoul2026/bella-eileen-2"))).toBe("贝拉 × 乃琳 02");
    expect(photoName(find("photo:asoul2026/group-4"))).toBe("A-SOUL 04");
    expect(photoNo(find("photo:asoul2026/bella-eileen-2"))).toBe("02");
  });

  it("shelves the album by member, then the shared cards", () => {
    const sections = albumSections(items);
    expect(sections.map((s) => [s.label, s.items.length, s.wide])).toEqual([
      ["嘉然", 8, false], ["贝拉", 8, false], ["乃琳", 8, false], ["双人", 6, true], ["团体", 4, true],
    ]);
    expect(sections[0]!.items.map((i) => i.kind)).toEqual([...Array(4).fill("solo"), ...Array(4).fill("sign")]);
  });

  it("filters by kind and by what the save holds", () => {
    const owned = new Set(["photo:asoul2026/diana-1", "sign:asoul2026/bella-2"]);
    expect(filterPhotos(items, "sign", owned)).toHaveLength(12);
    expect(filterPhotos(items, "owned", owned).map((i) => i.id)).toEqual([...owned]);
    expect(filterPhotos(items, "missing", owned)).toHaveLength(items.length - 2);
    expect(filterPhotos(items, "all", owned)).toHaveLength(items.length);
  });
});
