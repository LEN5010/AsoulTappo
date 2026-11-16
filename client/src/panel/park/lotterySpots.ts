// A spot is the centre of a digit on screen and its font size; the spots on the number keys are kept from the keys'
// top left corner, since the keys can move between a purchase and the flight of its number.

export interface Spot { d: string; x: number; y: number; size: number }

export function spotOf(el: Element | null | undefined, d: string): Spot | null {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { d, x: r.left + r.width / 2, y: r.top + r.height / 2, size: parseFloat(getComputedStyle(el).fontSize) || 72 };
}

/** [spots] measured from the top left corner of [keys]. */
export function onKeys(keys: HTMLElement | undefined, spots: (Spot | null)[]): Spot[] {
  const box = keys?.getBoundingClientRect();
  if (!box) return [];
  return spots.flatMap((p) => (p ? { ...p, x: p.x - box.left, y: p.y - box.top } : []));
}
