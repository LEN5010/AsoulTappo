import { describe, expect, it } from "vitest";
import { compareVersions, isNewer } from "./semver";

describe("compareVersions", () => {
  it.each([
    ["0.1.0-beta.7", "0.1.0-beta.6", 1],
    ["0.1.0-beta.10", "0.1.0-beta.9", 1],
    ["0.1.0", "0.1.0-beta.9", 1],
    ["0.1.0-beta.6", "0.1.0-beta.6", 0],
    ["0.1.0-beta", "0.1.0-beta.1", -1],
    ["0.1.0-alpha.2", "0.1.0-beta.1", -1],
    ["v0.2.0", "0.1.9", 1],
    ["1.0.0", "0.99.0", 1],
  ])("%s vs %s", (a, b, sign) => {
    expect(Math.sign(compareVersions(a, b)!)).toBe(sign);
  });

  it("refuses what is not a version", () => {
    expect(compareVersions("latest", "0.1.0")).toBeNull();
    expect(isNewer("latest", "0.1.0")).toBe(false);
  });
});
