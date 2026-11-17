// The global shortcuts as the settings page records and shows them. Stored as the shortcut the system registers:
// modifiers then one key code, "Control+Alt+KeyH". The emote keys share their modifiers and end in 1 to 8, so only the
// modifiers are stored ("Control+Alt").

const MODIFIER_CODES = /^(Control|Alt|Shift|Meta|OS)(Left|Right)$/;
/** Keys a shortcut may end in: letters, digits, function keys and a few named ones. */
const KEY_CODES = /^(Key[A-Z]|Digit[0-9]|F([1-9]|1[0-9]|2[0-4])|Space|Backquote|Minus|Equal|Arrow(Up|Down|Left|Right)|Home|End|PageUp|PageDown|Insert|Delete)$/;
const FUNCTION_KEY = /^F\d+$/;

export interface KeyPress { code: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }

/**
 * The shortcut a key press stands for, or null while only modifiers are down or the key cannot be used.
 * A function key works alone; any other key needs Ctrl, Alt or the system key, so typing never triggers it.
 */
export function shortcutOf(e: KeyPress): string | null {
  if (MODIFIER_CODES.test(e.code) || !KEY_CODES.test(e.code)) return null;
  const mods = [e.ctrlKey && "Control", e.altKey && "Alt", e.shiftKey && "Shift", e.metaKey && "Super"].filter(Boolean);
  if (!FUNCTION_KEY.test(e.code) && !(e.ctrlKey || e.altKey || e.metaKey)) return null;
  return [...mods, e.code].join("+");
}

const NAMES: Record<string, string> = {
  Control: "Ctrl", Backquote: "`", Minus: "-", Equal: "=",
  ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→",
};

/** "Control+Alt+KeyH" as "Ctrl+Alt+H"; the system key is Cmd on macOS and Win elsewhere. */
export function shortcutLabel(keys: string, mac = false): string {
  return keys.split("+").map((k) => {
    if (k === "Super") return mac ? "Cmd" : "Win";
    if (k === "Alt" && mac) return "Option";
    return NAMES[k] ?? k.replace(/^(Key|Digit)/, "");
  }).join("+");
}

/** How many quick emotes have a key: the strip holds this many at most. */
export const EMOTE_KEYS = 8;

/** The modifiers of a press on a digit ("Control+Alt"), for the emote keys; null for any other press. */
export function emoteModsOf(e: KeyPress): string | null {
  return shortcutOf(e)?.match(/^(.+)\+Digit[0-9]$/)?.[1] ?? null;
}

/** The shortcut of the quick emote at [place] (from 1) under the stored modifiers. */
export function emoteShortcut(mods: string, place: number): string {
  return `${mods}+Digit${place}`;
}

/** "Control+Alt" as "Ctrl+Alt+1~8". */
export function emoteKeysLabel(mods: string, mac = false): string {
  return `${shortcutLabel(mods, mac)}+1~${EMOTE_KEYS}`;
}

/**
 * Registers the emote keys under [mods] through [set] ("" removes them all). When the system refuses one of them the
 * others are removed again and the refusal is thrown: the keys work as a row or not at all.
 */
export async function setEmoteKeys(mods: string, set: (slot: `emote-${number}`, keys: string) => Promise<void>): Promise<void> {
  const places = Array.from({ length: EMOTE_KEYS }, (_, i) => i + 1);
  try {
    for (const n of places) await set(`emote-${n}`, mods ? emoteShortcut(mods, n) : "");
  } catch (e) {
    for (const n of places) await set(`emote-${n}`, "").catch(() => {});
    throw e;
  }
}
