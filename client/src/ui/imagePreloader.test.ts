import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createImagePreloader } from "./imagePreloader";
const images: FakeImage[] = [];
class FakeImage {
  src = "";
  done!: () => void;
  fail!: () => void;
  removeAttribute = vi.fn();
  pending = new Promise<void>((resolve, reject) => { this.done = resolve; this.fail = () => reject(new Error("decode")); });
  decode = () => this.pending;
  constructor() { images.push(this); }
}
const settle = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
beforeEach(() => { images.length = 0; vi.stubGlobal("Image", FakeImage); });
afterEach(() => vi.unstubAllGlobals());
it("only decodes two unique look-ahead images, not the entire result", () => {
  createImagePreloader().setWindow(["a", "a", "b", "c"]);
  expect(images.map((i) => i.src)).toEqual(["a", "b"]);
});
it("keeps a strict concurrency cap when the spotlight changes before decoding settles", async () => {
  const p = createImagePreloader(); p.setWindow(["a", "b"]); p.setWindow(["c", "d"]);
  expect(images).toHaveLength(2);
  expect(images.every((i) => i.removeAttribute.mock.calls.length === 1)).toBe(true);
  images[0]!.done(); await settle(); expect(images.map((i) => i.src)).toEqual(["a", "b", "c"]);
  images[1]!.fail(); await settle(); expect(images.map((i) => i.src)).toEqual(["a", "b", "c", "d"]);
});
it("keeps decoded art only while in the look-ahead window", async () => {
  const p = createImagePreloader(); p.setWindow(["a", "b"]);
  images[0]!.done(); images[1]!.done(); await settle();
  p.setWindow(["b", "c"]); expect(images).toHaveLength(3);
  expect(images[0]!.removeAttribute).toHaveBeenCalledWith("src");
  expect(images[1]!.removeAttribute).not.toHaveBeenCalled();
  p.clear(); images[2]!.done(); await settle(); expect(images).toHaveLength(3);
  expect(images[1]!.removeAttribute).toHaveBeenCalledWith("src");
});
it("does not loop on a failed image and re-decodes cancelled art if requested again", async () => {
  const p = createImagePreloader(); p.setWindow(["a"]); images[0]!.fail(); await settle();
  p.setWindow(["a"]); expect(images).toHaveLength(1);
  p.setWindow(["b"]); p.clear(); p.setWindow(["b"]);
  images[1]!.fail(); await settle(); expect(images.map((i) => i.src)).toEqual(["a", "b", "b"]);
});
