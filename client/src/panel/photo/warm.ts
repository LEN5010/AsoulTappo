// What the shelf shows first, made ready while the pointer is on its way to the pool's tab: the canvas and its programs,
// the box's print and the signatures. What a box is opened with waits for the shelf (PhotoShelf.vue); what was made
// ready and never shown is let go of a while later (engine.ts).
import { photoGl } from "../../photo/engine";
import { shopSeries } from "./shop";

export function warmShelf(): void {
  const series = shopSeries.value;
  if (series) void photoGl().then((gl) => {
    if (!gl) return;
    void gl.kit.ink(series);
    void gl.kit.signs(series);
  });
}
