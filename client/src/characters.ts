// Character assets live in src/assets/characters/<name>/{bgImage,keyboardImage,mouseImage,leftClickImage,rightClickImage}.webp
// Pet images under assets/characters (copyright: assets/characters/COPYRIGHT.md).
// A skin is a folder whose name starts with its member, such as 贝拉山海经: only bgImage.webp
// is required, the other layers come from the member. A two-form skin also has formImage.webp, its second picture
// on the same canvas (pet/SkinForm.ts says when it shows), and may have formLoop.webp: frames of one part of the
// second picture, side by side, that play over it while it shows (formLoop.json says where; scripts/make_form_loop.py).
import { memberOf } from "./manifest";

const files = import.meta.glob("./assets/characters/*/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

/** Where the frames of a form loop go, in pixels of the second picture (`width` x `height`). */
export interface FormLoopSpec {
  x: number;
  y: number;
  w: number;
  h: number;
  frames: number;
  /** each frame shows this long */
  ms: number;
  width: number;
  height: number;
  /** Drawn behind the second picture instead of over it: wings that grow from the back under the long hair, an instrument floating behind the head. */
  behind?: boolean;
  /** How the loop comes and goes with the second form. Without it, a fade; `summon`: it spins up out of a flash of
   *  light and folds back into one. */
  entrance?: "summon";
}
const loops = import.meta.glob("./assets/characters/*/formLoop.json", { eager: true, import: "default" }) as Record<string, FormLoopSpec>;

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
  /** The second picture of a two-form skin, in the same three sizes as `bg`. */
  form?: { bg: string; bgSmall: string; bgMedium: string; loop?: FormLoopSpec & { src: string } };
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
    const loop = loops[`./assets/characters/${name}/formLoop.json`];
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
      ...(own.formImage ? {
        form: {
          bg: own.formImage,
          bgSmall: preview(name, "form-480") ?? own.formImage,
          bgMedium: preview(name, "form-960") ?? own.formImage,
          ...(own.formLoop && loop ? { loop: { ...loop, src: own.formLoop } } : {}),
        },
      } : {}),
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

/** How far, in base canvas px, the second form's loop draws past the right edge of the picture (嘉然然龙's open wing). */
export function formReach(name: string): number {
  const l = getCharacter(name)?.form?.loop;
  return l ? Math.max(0, ((l.x + l.w) / l.width - 1) * PET_BASE.width) : 0;
}

/** Skin folder names are the member name followed by the collection name. */
export const skinSeries = (name: string) => name.slice(memberOf(name).length);

// Layout of the layers on the 240x135 base canvas.
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
  嘉然冬日奇迹: { x: 152, y: 0 },
  贝拉冬日奇迹: { x: 146, y: -1 },
  乃琳冬日奇迹: { x: 150, y: 3 },
  // Two-form skins: the first form's head; the second only adds horns, fire or a crown around it.
  嘉然然龙: { x: 152, y: 7 },
  乃琳法师: { x: 150, y: 14 },
  贝拉炎头队长: { x: 146, y: 5 },
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
