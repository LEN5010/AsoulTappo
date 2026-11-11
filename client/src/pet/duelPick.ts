// A click on a partner's pet shows a row of keys over that pet: poke, rock-paper-scissors (whose key opens the bets)
// and, for a partner wearing a big hidden card's plate, a look at that card. One such bubble at a time.
import { computed, ref, watch } from "vue";
import type { Member } from "../net/protocol";
import { canDuel, canPoke, inviteDuel, members, poke } from "../stores/room";
import { openPanel } from "../stores/ui";
import type { Pos, Size } from "../stores/desk";
import { plateCard } from "./plates";

/** The bubble closes after this long without the pointer on it. */
export const PICK_MS = 6000;
/** Sizes of the bubble's two steps, for placing it on screen: the row of keys (ASK_WIDTH with one key), then the bets. */
export const ASK_WIDTH = 96;
const KEY_WIDTH = 76;
const KEY_GAP = 6;
export const ASK_HEIGHT = 50;
export const PICK_WIDTH = 236;
export const PICK_HEIGHT = 84;
/** Width of the duel bubble over the own pet, the same for every step, and its height at most. */
export const DUEL_WIDTH = 212;
export const DUEL_HEIGHT = 142;
/** Size of the bubble over the own pet after a poke (PokeBubble.vue). */
export const POKED_WIDTH = 168;
export const POKED_HEIGHT = 74;

/** Member id whose pet shows the bubble, null for none. */
export const picking = ref<string | null>(null);
/** False while the bubble shows the single key, true once it was pressed and the bets are out. */
export const staking = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

export interface PickKeys { poke: boolean; duel: boolean; plate: string | null }
const keysFor = (m: Member | undefined): PickKeys =>
  m ? { poke: canPoke(m), duel: canDuel(m), plate: plateCard(m.plate)?.id ?? null } : { poke: false, duel: false, plate: null };
const anyKey = (k: PickKeys) => k.poke || k.duel || !!k.plate;
/** The keys the open bubble shows. */
export const pickKeys = computed(() => keysFor(picking.value ? members.get(picking.value) : undefined));
const keyCount = () => [pickKeys.value.poke, pickKeys.value.duel, !!pickKeys.value.plate].filter(Boolean).length;
/** Width of the row of keys. */
export const askWidth = (): number => {
  const n = Math.max(1, keyCount());
  return ASK_WIDTH + (n - 1) * (KEY_WIDTH + KEY_GAP);
};

/** Shows the keys over [m] when any applies to it; otherwise the click does nothing. */
export function openPick(m: Member): boolean {
  if (!anyKey(keysFor(m))) return false;
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
export const pickSize = (): Size => (staking.value ? { w: PICK_WIDTH, h: PICK_HEIGHT } : { w: askWidth(), h: ASK_HEIGHT });

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

/** Pokes the partner and closes the bubble. */
export function pickPoke(): void {
  const id = picking.value;
  closePick();
  if (id) poke(id);
}

/** Opens the panel on the card of the partner's plate, shown as a preview (src/panel/CollectionPage.vue). */
export function pickPlate(): void {
  const card = pickKeys.value.plate;
  closePick();
  if (card) openPanel("dex", { craftTarget: `view:card:${card}` });
}

/** Whether a press at [target] leaves the bubble alone: on the bubble itself. */
export const insidePick = (target: EventTarget | null): boolean =>
  !!(target as Element | null)?.closest?.("[data-duel-pick]");

// It also closes when the partner leaves, or nothing it offers is possible any more; the bets close once a duel is not.
watch(() => !picking.value || (staking.value ? pickKeys.value.duel : anyKey(pickKeys.value)),
  (ok) => { if (!ok) closePick(); }, { flush: "sync" });

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
