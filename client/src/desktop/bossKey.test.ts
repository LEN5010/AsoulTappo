import { describe, expect, it, vi } from "vitest";
import { emoteKeysLabel, emoteModsOf, setEmoteKeys, shortcutLabel, shortcutOf } from "./bossKey";

const press = (code: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  ({ code, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("the hide key", () => {
  it("is modifiers and one key, in a fixed order", () => {
    expect(shortcutOf(press("KeyH", { altKey: true, ctrlKey: true }))).toBe("Control+Alt+KeyH");
    expect(shortcutOf(press("Digit1", { metaKey: true, shiftKey: true }))).toBe("Shift+Super+Digit1");
  });

  it("waits while only modifiers are down", () => {
    expect(shortcutOf(press("ControlLeft", { ctrlKey: true }))).toBeNull();
    expect(shortcutOf(press("ShiftRight", { shiftKey: true }))).toBeNull();
  });

  it("takes a function key alone, and no other key without Ctrl, Alt or the system key", () => {
    expect(shortcutOf(press("F8"))).toBe("F8");
    expect(shortcutOf(press("KeyH"))).toBeNull();
    expect(shortcutOf(press("KeyH", { shiftKey: true }))).toBeNull();
    expect(shortcutOf(press("Enter", { ctrlKey: true }))).toBeNull();
  });

  it("is shown the way the keys are printed", () => {
    expect(shortcutLabel("Control+Alt+KeyH")).toBe("Ctrl+Alt+H");
    expect(shortcutLabel("Shift+Super+Digit1")).toBe("Shift+Win+1");
    expect(shortcutLabel("Alt+Super+ArrowUp", true)).toBe("Option+Cmd+↑");
    expect(shortcutLabel("F8")).toBe("F8");
  });
});

describe("the emote keys", () => {
  it("are recorded as the modifiers of a press on a digit", () => {
    expect(emoteModsOf(press("Digit3", { ctrlKey: true, altKey: true }))).toBe("Control+Alt");
    expect(emoteModsOf(press("Digit0", { metaKey: true }))).toBe("Super");
    expect(emoteModsOf(press("KeyH", { ctrlKey: true }))).toBeNull();
    expect(emoteModsOf(press("Digit3", { shiftKey: true }))).toBeNull();
    expect(emoteKeysLabel("Control+Alt")).toBe("Ctrl+Alt+1~8");
  });

  it("are registered one for each place", async () => {
    const set = vi.fn(async () => {});
    await setEmoteKeys("Control+Alt", set);
    expect(set).toHaveBeenCalledTimes(8);
    expect(set).toHaveBeenNthCalledWith(1, "emote-1", "Control+Alt+Digit1");
    expect(set).toHaveBeenNthCalledWith(8, "emote-8", "Control+Alt+Digit8");
    set.mockClear();
    await setEmoteKeys("", set);
    expect(set).toHaveBeenNthCalledWith(5, "emote-5", "");
  });

  it("are all removed when the system refuses one", async () => {
    const held: Record<string, string> = {};
    const set = vi.fn(async (slot: string, keys: string) => {
      if (keys.endsWith("Digit3")) throw "taken";
      held[slot] = keys;
    });
    await expect(setEmoteKeys("Alt", set)).rejects.toBe("taken");
    expect(Object.values(held).filter(Boolean)).toEqual([]);
  });
});
