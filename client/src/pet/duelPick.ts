// Inviting from the desk: a click on a partner's pet shows one key over that pet, and pressing it opens the bets.
// One such bubble at a time.
import { ref, watch } from "vue";
import type { Member } from "../net/protocol";
import { canDuel, inviteDuel, members } from "../stores/room";
import type { Pos, Size } from "../stores/desk";

/** The bubble closes after this long without the pointer on it. */
export const PICK_MS = 6000;
/** Sizes of the bubble's two steps, for placing it on screen: the single key, then the bets. */
export const ASK_WIDTH = 96;
export const ASK_HEIGHT = 50;
export const PICK_WIDTH = 236;
export const PICK_HEIGHT = 84;
/** Width of the duel bubble over the own pet, the same for every step, and its height at most. */
export const DUEL_WIDTH = 212;
export const DUEL_HEIGHT = 142;

/** Member id whose pet shows the bubble, null for none. */
export const picking = ref<string | null>(null);
/** False while the bubble shows the single key, true once it was pressed and the bets are out. */
export const staking = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

/** Shows the key over [m] when a duel with it looks possible; otherwise the click does nothing. */
export function openPick(m: Member): boolean {
  if (!canDuel(m)) return false;
  picking.value = m.id;
  staking.value = false;
  keepPick();
  return true;
}

/** The key was pressed: the bubble turns into the bets. */
export function showStakes(): void {
  if (!picking.value) return;
  staking.value = true;
  keepPick();
}

/** Size of the bubble as it shows now. */
export const pickSize = (): Size => (staking.value ? { w: PICK_WIDTH, h: PICK_HEIGHT } : { w: ASK_WIDTH, h: ASK_HEIGHT });

/** Restarts the countdown to closing while the bubble is in use. */
export function keepPick(): void {
  clearTimeout(timer);
  if (picking.value) timer = setTimeout(closePick, PICK_MS);
}

export function closePick(): void {
  clearTimeout(timer);
  picking.value = null;
  staking.value = false;
}

/** Sends the invite at [bet] and closes the bubble. */
export function pickStake(bet: number): void {
  const id = picking.value;
  closePick();
  if (id) inviteDuel(id, bet);
}

/** Whether a press at [target] leaves the bubble alone: on the bubble itself. */
export const insidePick = (target: EventTarget | null): boolean =>
  !!(target as Element | null)?.closest?.("[data-duel-pick]");

// It also closes when the partner leaves, a duel starts, or anything else makes a duel with it impossible.
watch(() => {
  const id = picking.value;
  const m = id ? members.get(id) : undefined;
  return !id || (!!m && canDuel(m));
}, (ok) => { if (!ok) closePick(); }, { flush: "sync" });

/**
 * Where a bubble over a pet goes: shifted sideways to stay [margin] inside the screen, and under the pet when there is
 * no room above it. [pos] and [size] are the pet's box, [bubble] the bubble's size.
 */
export function bubblePlacement(pos: Pos, size: Size, bubble: Size, screen: Size, margin = 8): { shift: number; below: boolean } {
  const left = pos.x + size.w / 2 - bubble.w / 2;
  const fitted = Math.min(Math.max(left, margin), Math.max(margin, screen.w - margin - bubble.w));
  // 8px gap and the 7px point between the bubble and the pet
  return { shift: Math.round(fitted - left), below: pos.y - bubble.h - 15 < margin };
}
