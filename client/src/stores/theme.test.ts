import { describe, expect, it } from "vitest";
import { THEME_COLORS, themeTokens } from "./theme";

describe("theme colors", () => {
  it("offers the brand color and one color per member", () => {
    expect(THEME_COLORS.map((t) => t.id)).toEqual(["asoul", "jiaran", "nailin", "beila", "xinyi", "sinuo"]);
  });
  it("leaves the brand palette to tokens.css", () => {
    expect(themeTokens("asoul")).toEqual({});
  });
  it("falls back to the brand palette on an unknown id", () => {
    expect(themeTokens("gone")).toEqual({});
  });
  it("derives the page colors from a member color", () => {
    expect(themeTokens("nailin")["--accent"]).toBe("#576690");
    expect(themeTokens("nailin")["--page"]).toBeDefined();
  });
});
