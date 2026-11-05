import { describe, expect, it } from "vitest";
import { THEME_COLORS, themeTokens } from "./theme";

describe("theme colors", () => {
  it("offers the brand color and one color per member", () => {
    expect(THEME_COLORS.map((t) => t.id)).toEqual(["asoul", "jiaran", "nailin", "beila", "xinyi", "sinuo"]);
    expect(THEME_COLORS.map((t) => t.color)).toEqual(["#FC966E", "#F48FB1", "#4F63C9", "#EE7F78", "#D02F7C", "#7A52D6"]);
  });
  it("leaves the brand palette to tokens.css", () => {
    expect(themeTokens("asoul")).toEqual({});
  });
  it("falls back to the brand palette on an unknown id", () => {
    expect(themeTokens("gone")).toEqual({});
  });
  it("derives the page colors from a member color", () => {
    expect(themeTokens("nailin")["--accent"]).toBe("#4F63C9");
    expect(themeTokens("nailin")["--page"]).toBeDefined();
  });
  it("keeps every gradient within its own hue family", () => {
    expect(themeTokens("nailin")["--tone-bottom"]).toBe("#8A3CF0");
    expect(themeTokens("sinuo")["--tone-top"]).toBe("#7FB0FF");
  });
});
