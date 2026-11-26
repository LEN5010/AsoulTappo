// What the shelf draws with, made ready while the pointer is on its way to the pool's tab.
import { photoGl } from "../../photo/engine";
import { shopSeries } from "./shop";

export function warmShelf(): void {
  const series = shopSeries.value;
  if (series) void photoGl().then((gl) => gl?.kit.load(series));
}
