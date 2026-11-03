// Character assets live in src/assets/characters/<name>/{bgImage,keyboardImage,mouseImage,leftClickImage,rightClickImage}.png
// Imported from Evelynall/ASoul-Little-Bun (see assets/characters/COPYRIGHT.md).
const files = import.meta.glob("./assets/characters/*/*.png", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

export interface CharacterAssets {
  name: string;
  bg: string;
  keyboard: string;
  mouse: string;
  leftClick: string;
  rightClick: string;
}

function build(): Record<string, CharacterAssets> {
  const tmp: Record<string, Record<string, string>> = {};
  for (const [path, url] of Object.entries(files)) {
    const m = path.match(/characters\/([^/]+)\/([^/]+)\.png$/);
    if (!m) continue;
    (tmp[m[1]] ??= {})[m[2]] = url;
  }
  const out: Record<string, CharacterAssets> = {};
  for (const [name, f] of Object.entries(tmp)) {
    if (!f.bgImage || !f.keyboardImage || !f.mouseImage) continue;
    out[name] = {
      name,
      bg: f.bgImage,
      keyboard: f.keyboardImage,
      mouse: f.mouseImage,
      leftClick: f.leftClickImage ?? f.mouseImage,
      rightClick: f.rightClickImage ?? f.mouseImage,
    };
  }
  return out;
}

export const characters = build();
export const characterNames = Object.keys(characters);
export const defaultCharacter = characterNames[0] ?? "";

/** Resolve a (possibly unknown, e.g. from a remote client) name to assets. */
export function getCharacter(name: string): CharacterAssets | undefined {
  return characters[name] ?? characters[defaultCharacter];
}

// Layout of the layers on the 240x135 base canvas (from the original app's defaults).
export const PET_BASE = {
  width: 240,
  height: 135,
  keyboard: { x: 94, y: 84, size: 25, pressOffset: 5 },
  mouse: { x: 190, y: 90, size: 25, maxOffset: 20 },
};
