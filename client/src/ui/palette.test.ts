import { describe, expect, it } from "vitest";
import { accentTokens, contrast } from "./palette";

// tokens.css
const INK_3 = "#766D7C";
const SUPPORT_COLORS = ["#E799B0", "#576690", "#BD7D74", "#F27BA9", "#3F5FA8"];

describe("accentTokens", () => {
  it.each(SUPPORT_COLORS)("keeps %s readable", (color) => {
    const t = accentTokens(color);
    expect(contrast(t["--accent"]!, t["--on-accent"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--accent-hover"]!, t["--on-accent"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--accent-deep"]!, t["--page"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(INK_3, t["--page"]!)).toBeGreaterThanOrEqual(4.5);
  });
  it("leaves a color alone when it already passes", () => {
    expect(accentTokens("#576690")["--accent"]).toBe("#576690");
    expect(accentTokens("#576690")["--on-accent"]).toBe("#FFFFFF");
  });
  it("picks dark text on a light accent", () => {
    expect(accentTokens("#E799B0")["--on-accent"]).toBe("#2B2530");
  });
});
