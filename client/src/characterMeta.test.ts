import { describe, expect, it } from "vitest";
import { DEFAULT_CHARACTER, MEMBER_COLORS, MEMBER_NAMES, memberColorOf, memberNameOf } from "./characterMeta";
import { defaultCharacter } from "./characters";
import { characterColor, manifest, memberOf } from "./manifest";

describe("characterMeta contract", () => {
  it("stays in step with the asset manifest's members, colors, and default character", () => {
    expect([...MEMBER_NAMES]).toEqual(manifest.characters.map((c) => c.name));
    expect(DEFAULT_CHARACTER).toBe(defaultCharacter);
    for (const c of manifest.characters) {
      expect(MEMBER_COLORS[c.name]).toBe(c.color);
      expect(memberColorOf(c.name)).toBe(characterColor(c.name));
    }
    for (const skin of manifest.skins) {
      expect(memberNameOf(skin.name)).toBe(memberOf(skin.name));
      expect(memberColorOf(skin.name)).toBe(characterColor(skin.name));
    }
  });
});
