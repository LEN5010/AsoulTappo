// Guards the keys that answer a dou dizhu invite (the room page's banner, the pet's bubble) against an invite that
// takes the place of the one on screen under the pointer: the panel hears of a new invite up to 50 ms late
// (desktop/bridge.ts), and accepting a table of the queue pays its deposit. A click answers only the invite its key
// went down on, and an accept counts only INVITE_SETTLE_MS after the invite on screen changed.
import { watch } from "vue";

/** An accept this soon after the invite on screen changed (one coming up from none included) is dropped. */
export const INVITE_SETTLE_MS = 400;

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
  let pressed: string | undefined;
  return {
    show(table) {
      if (table === shown) return;
      shown = table;
      since = now();
      pressed = undefined;
    },
    press() {
      pressed = shown;
    },
    pick(accept, pointer) {
      const down = pressed;
      pressed = undefined;
      if (!shown || (pointer && down !== shown)) return null;
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
