import { describe, expect, it } from "vitest";
import { accentTokens, contrast } from "./palette";

// tokens.css
const INK_3 = "#766D7C";
const SUPPORT_COLORS = ["#F48FB1", "#4F63C9", "#EE7F78", "#D02F7C", "#7A52D6"];

describe("accentTokens", () => {
  it.each(SUPPORT_COLORS)("keeps %s readable", (color) => {
    const t = accentTokens(color);
    expect(t["--accent"]).toBe(color);
    expect(contrast(t["--accent"]!, t["--on-accent"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--accent-hover"]!, t["--on-accent"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--accent-deep"]!, t["--page"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(INK_3, t["--page"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--accent-surface"]!, t["--on-accent-surface"]!)).toBeGreaterThanOrEqual(4.5);
  });
  it("keeps warm text tones red-dominant rather than brown", () => {
    const deep = accentTokens("#EE7F78")["--accent-deep"]!;
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(deep.slice(i, i + 2), 16)) as [number, number, number];
    expect(b).toBeGreaterThanOrEqual(g);
    expect(r).toBeGreaterThan(b);
  });
  it("leaves a color alone when it already passes", () => {
    expect(accentTokens("#576690")["--accent"]).toBe("#576690");
    expect(accentTokens("#576690")["--on-accent"]).toBe("#FFFFFF");
  });
  it("picks dark text on a light accent", () => {
    expect(accentTokens("#E799B0")["--on-accent"]).toBe("#2B2530");
  });
});
