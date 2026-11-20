// Guards the keys that answer a dou dizhu invite (the room page's banner, the pet's bubble) against an invite that
// takes the place of the one on screen under the pointer: the panel hears of a new invite up to 50 ms late
// (desktop/bridge.ts), and accepting a table of the queue pays its deposit. A click whose key went down on another
// invite, or while the invite on screen changed, is dropped; one whose key going down was not seen (a window in the
// background may swallow it) counts. An accept counts only INVITE_SETTLE_MS after the invite on screen changed.
import { watch } from "vue";

/** An accept this soon after the invite on screen changed (one coming up from none included) is dropped. */
export const INVITE_SETTLE_MS = 400;
/** A key that was down when the invite on screen changed. */
const STALE = Symbol("stale");

export interface InviteKeys {
  /** The invite on screen is now table [table]; undefined for none. */
  show(table: string | undefined): void;
  /** A key went down. */
  press(): void;
  /** The table a click answers, or null to drop it; [pointer] for a click of the pointer, not of the keyboard. */
  pick(accept: boolean, pointer: boolean): string | null;
}

export function inviteKeys(now: () => number = Date.now): InviteKeys {
  let shown: string | undefined;
  let since = -Infinity;
  // The invite a key went down on, STALE, or undefined when no key went down since the last click.
  let pressed: string | undefined | typeof STALE;
  return {
    show(table) {
      if (table === shown) return;
      shown = table;
      since = now();
      if (pressed !== undefined) pressed = STALE;
    },
    press() {
      pressed = shown;
    },
    pick(accept, pointer) {
      const down = pressed;
      pressed = undefined;
      if (!shown || (pointer && down !== undefined && down !== shown)) return null;
      if (accept && now() - since < INVITE_SETTLE_MS) return null;
      return shown;
    },
  };
}

/** The guard for a component showing the invite [shown]: wire `press` to pointerdown and `answer` to click. */
export function useInviteKeys(shown: () => string | undefined, answer: (accept: boolean, table: string) => void) {
  const keys = inviteKeys();
  watch(shown, (table) => keys.show(table), { immediate: true, flush: "sync" });
  return {
    press: () => keys.press(),
    answer(accept: boolean, e: MouseEvent) {
      const table = keys.pick(accept, e.detail > 0);
      if (table) answer(accept, table);
    },
  };
}
