import { describe, expect, it } from "vitest";
import { memberTone } from "./reveal-board";

describe("memberTone", () => {
  it("fills a skin's reveal with its member's colour", () => {
    const tone = memberTone("乃琳");
    expect(tone["--tone-fill"]).toContain("#4F63C9");
    expect(tone["--tone-glow"]).toBe("rgba(79, 99, 201, 0.72)");
    expect(tone["--tone-ink"]).toBe("#fff");
  });
  it("writes in dark ink on the light member colours", () => {
    expect(memberTone("嘉然")["--tone-ink"]).toBe("var(--ink)");
    expect(memberTone("贝拉")["--tone-ink"]).toBe("var(--ink)");
  });
  it("leaves an unknown skin to the default tone", () => {
    expect(memberTone("nobody")).toEqual({});
  });
});
