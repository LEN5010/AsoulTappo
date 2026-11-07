import { expect, it } from "vitest";
import { remotePetSize } from "./bounds";
import { PET_BASE } from "../characters";

it.each([false, true])("includes the minimum name width at 40 percent, plates=%s", (plates) => {
  const size = remotePetSize(0.4, true, plates);
  expect(size.w).toBe(120);
  const x = 1280 - size.w - 8;
  expect(x + 120).toBeLessThanOrEqual(1280 - 8);
});
it("does not reserve a name band while names are hidden", () => {
  expect(remotePetSize(0.4, false, true)).toEqual({ w: PET_BASE.width * 0.4, h: PET_BASE.height * 0.4 });
});
it("preserves normal-size bounds", () => {
  expect(remotePetSize(1, true, false)).toEqual({ w: PET_BASE.width, h: PET_BASE.height + 22 });
});
