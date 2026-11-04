import { describe, expect, it } from "vitest";
import { accentTokens, contrast } from "./palette";

const PAGE = "#FFF4EE";

describe("accentTokens", () => {
  it.each(["#4C2F7B", "#E4A98B", "#BB7196", "#BE98AA", "#88535F"])("keeps %s readable", (color) => {
    const t = accentTokens(color);
    expect(contrast(t["--accent"]!, t["--on-accent"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--accent-deep"]!, PAGE)).toBeGreaterThanOrEqual(4.5);
  });
  it("leaves a color alone when it already passes", () => {
    expect(accentTokens("#4C2F7B")["--accent"]).toBe("#4C2F7B");
    expect(accentTokens("#4C2F7B")["--on-accent"]).toBe("#FFFFFF");
  });
  it("picks dark text on a light accent", () => {
    expect(accentTokens("#E4A98B")["--on-accent"]).toBe("#2B2530");
  });
});
