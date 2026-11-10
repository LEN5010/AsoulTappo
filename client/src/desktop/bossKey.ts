// The hide key as the settings page records and shows it. Stored as the shortcut the system registers:
// modifiers then one key code, "Control+Alt+KeyH".

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
