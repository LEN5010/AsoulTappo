// The arithmetic of dragging a showcase card along the row on the own namecard (ProfileCard.vue).

/** The slot whose centre is nearest to [x]; the first of two as near. */
export function nearestSlot(centers: number[], x: number): number {
  return centers.reduce((best, c, i) => (Math.abs(c - x) < Math.abs(centers[best] - x) ? i : best), 0);
}

/** Where card [i] stands while the card from slot [from] is held over slot [to]: the cards between move one slot
 * toward [from]. */
export function slotWhileDragging(i: number, from: number, to: number): number {
  if (from < to && i > from && i <= to) return i - 1;
  if (to < from && i >= to && i < from) return i + 1;
  return i;
}

/** [ids] with the one at [from] moved to [to]. */
export function moved<T>(ids: readonly T[], from: number, to: number): T[] {
  const out = [...ids];
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}
