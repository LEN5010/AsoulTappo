// Character assets live in src/assets/characters/<name>/{bgImage,keyboardImage,mouseImage,leftClickImage,rightClickImage}.webp
// Pet images under assets/characters (copyright: assets/characters/COPYRIGHT.md).
// A skin is a folder whose name starts with its member, such as 贝拉山海经: only bgImage.webp
// is required, the other layers come from the member.
import { memberOf } from "./manifest";

const files = import.meta.glob("./assets/characters/*/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

const previews = import.meta.glob("./assets/previews/characters/*/*.webp", {
  eager: true, query: "?url", import: "default",
}) as Record<string, string>;
const preview = (name: string, kind: string) => previews[`./assets/previews/characters/${name}/${kind}.webp`];

export interface CharacterAssets {
  name: string;
  bg: string;
  bgSmall: string;
  bgMedium: string;
  portrait: string;
  keyboard: string;
  mouse: string;
  leftClick: string;
  rightClick: string;
}

function build(): Record<string, CharacterAssets> {
  const tmp: Record<string, Record<string, string>> = {};
  for (const [path, url] of Object.entries(files)) {
    const m = path.match(/characters\/([^/]+)\/([^/]+)\.webp$/);
    if (!m) continue;
    (tmp[m[1]] ??= {})[m[2]] = url;
  }
  const out: Record<string, CharacterAssets> = {};
  for (const [name, own] of Object.entries(tmp)) {
    const f = { ...tmp[memberOf(name)], ...own };
    if (!f.bgImage || !f.keyboardImage || !f.mouseImage) continue;
    out[name] = {
      name,
      bg: f.bgImage,
      bgSmall: preview(name, "bg-480") ?? f.bgImage,
      bgMedium: preview(name, "bg-960") ?? f.bgImage,
      portrait: preview(name, "face") ?? "",
      keyboard: f.keyboardImage,
      mouse: f.mouseImage,
      leftClick: f.leftClickImage ?? f.mouseImage,
      rightClick: f.rightClickImage ?? f.mouseImage,
    };
  }
  return out;
}

export const characters = build();
const portraits = new Map(Object.values(characters).map((c) => [c.bg, c.portrait]));
export const portraitFor = (src: string) => portraits.get(src);
export const characterNames = Object.keys(characters);
export const defaultCharacter = characterNames[0] ?? "";

/** Resolve a (possibly unknown, e.g. from a remote client) name to assets. */
export function getCharacter(name: string): CharacterAssets | undefined {
  return characters[name] ?? characters[memberOf(name)] ?? characters[defaultCharacter];
}

/** Skin folder names are the member name followed by the collection name. */
export const skinSeries = (name: string) => name.slice(memberOf(name).length);

// Layout of the layers on the 240x135 base canvas (from the original app's defaults).
export const PET_BASE = {
  width: 240,
  height: 135,
  keyboard: { x: 94, y: 84, size: 25, pressOffset: 5 },
  mouse: { x: 190, y: 90, size: 25, maxOffset: 20 },
  /** top centre of the monitor in the background image: desk accessories stand here */
  monitor: { x: 50, y: 46 },
};

// Top of each character's head on the base canvas (measured from bgImage.webp).
// Head accessories sit here and emote bubbles grow from its upper right.
// Negative when the picture is taller than the canvas and the headwear reaches above it.
const HEADS: Record<string, { x: number; y: number }> = {
  嘉然: { x: 152, y: -4 },
  乃琳: { x: 150, y: 18 },
  贝拉: { x: 146, y: 10 },
  心宜: { x: 152, y: 10 },
  思诺: { x: 142, y: 9 },
  // Skins drawn on the member's layout whose head top differs from the member's.
  乃琳山海经: { x: 150, y: -11 },
  乃琳睡衣派对: { x: 150, y: 0 },
  嘉然山海经: { x: 152, y: 10 },
  嘉然睡衣派对: { x: 152, y: 10 },
  嘉然2025生日: { x: 152, y: -2 },
  贝拉2025生日: { x: 146, y: -10 },
  贝拉睡衣派对: { x: 146, y: -9 },
};
export function headAnchor(name: string): { x: number; y: number } {
  return HEADS[name] ?? HEADS[memberOf(name)] ?? { x: 150, y: 10 };
}

/**
 * Bounding region of the character alone on the 240x135 base canvas:
 * - Monitor ends at x = 86 (so x >= 90 has zero monitor)
 * - Desk bar starts at y = 113 (so y <= 112 has zero desk)
 * - Character spans x = 92..220, y = 0..112.
 */
export const FACE_CROP = { x: 90, y: 0, w: 132, h: 112, size: 122 };
