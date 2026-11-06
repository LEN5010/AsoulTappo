import { describe, expect, it } from "vitest";
import { characterColor, manifest } from "../manifest";
import { settings } from "./settings";
import { skinVars } from "./theme";

describe("skin", () => {
  it("follows the selected character", () => {
    const before = settings.character;
    for (const { name } of manifest.characters) {
      settings.character = name;
      expect(skinVars.value["--char"]).toBe(characterColor(name));
    }
    settings.character = before;
  });
});
