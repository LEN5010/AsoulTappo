import { expect, it } from "vitest";
import { remotePetSize } from "./bounds";
import { PET_BASE } from "../characters";

it.each([[false, 16], [true, 17]])("keeps names within a small partner, plates=%s", (plates, band) => {
  const size = remotePetSize(0.4, true, plates);
  expect(size.w).toBeCloseTo(PET_BASE.width * 0.4);
  expect(size.h).toBeCloseTo(PET_BASE.height * 0.4 + band);
});
it("does not reserve a name band while names are hidden", () => {
  expect(remotePetSize(0.4, false, true)).toEqual({ w: PET_BASE.width * 0.4, h: PET_BASE.height * 0.4 });
});
it("preserves normal-size bounds", () => {
  expect(remotePetSize(1, true, false)).toEqual({ w: PET_BASE.width, h: PET_BASE.height + 22 });
});
