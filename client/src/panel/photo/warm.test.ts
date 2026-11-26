// What the pointer on its way to the photocards' tab makes ready: what the shelf shows first, not what a box is opened with.
import { expect, it, vi } from "vitest";
import { ref } from "vue";

const kit = vi.hoisted(() => ({ ink: vi.fn(), signs: vi.fn(), load: vi.fn(), thumbs: vi.fn(), want: vi.fn() }));
vi.mock("../../photo/engine", () => ({ photoGl: async () => ({ kit }) }));
vi.mock("./shop", () => ({ shopSeries: ref("asoul2026") }));

it("makes ready the canvas, the box's print and the signatures alone", async () => {
  const { warmShelf } = await import("./warm");
  warmShelf();
  await vi.waitFor(() => expect(kit.ink).toHaveBeenCalledWith("asoul2026"));
  expect(kit.signs).toHaveBeenCalledWith("asoul2026");
  expect([kit.load, kit.thumbs, kit.want].map((f) => f.mock.calls.length)).toEqual([0, 0, 0]);
});
