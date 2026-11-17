// Whether the player agreed to the current texts and confirmed this version's statement that the app is free.
// Until both, the desk stays offline and the panel shows only the consent dialog; confirming in either window reaches
// the other through the settings sync.
//
// The texts are agreed to once per TERMS_VERSION. The statement is confirmed once per app version: the first start
// after every update (and after installing) opens the dialog, whose key stays locked for HOLD_MS.
import { computed } from "vue";
import { isTauri } from "../composables/tauri";
import { settings } from "../stores/settings";
import { APP_VERSION } from "../version";
import { TERMS_VERSION } from ".";

/** How long the dialog must have been in view before its key works. */
export const HOLD_MS = 3000;

/** The current texts were agreed to; the dialog then only asks to confirm the statement. */
export const termsCurrent = computed(() => settings.termsAgreed === TERMS_VERSION);
export const agreed = computed(() => termsCurrent.value && settings.statementSeen === APP_VERSION);

export function agree(): void {
  settings.termsAgreed = TERMS_VERSION;
  settings.statementSeen = APP_VERSION;
}

/** Whole seconds left of the hold after the dialog has been in view for [shownMs]; 0 once the key works. */
export function holdLeft(shownMs: number): number {
  return Math.max(0, Math.ceil((HOLD_MS - shownMs) / 1000));
}

/** Declining quits the app. The browser preview cannot quit, so the dialog stays. */
export async function declineAndQuit(): Promise<void> {
  if (!isTauri) return;
  const { exit } = await import("@tauri-apps/plugin-process");
  await exit(0);
}
