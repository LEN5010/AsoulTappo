import { describe, expect, it } from "vitest";
import { shortcutLabel, shortcutOf } from "./bossKey";

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
