// Whether the player agreed to the current texts. Until then the desk stays offline and the panel shows only the
// consent dialog; agreeing in either window reaches the other through the settings sync.
import { computed } from "vue";
import { isTauri } from "../composables/tauri";
import { settings } from "../stores/settings";
import { TERMS_VERSION } from ".";

export const agreed = computed(() => settings.termsAgreed === TERMS_VERSION);

export function agree(): void {
  settings.termsAgreed = TERMS_VERSION;
}

/** Declining quits the app. The browser preview cannot quit, so the dialog stays. */
export async function declineAndQuit(): Promise<void> {
  if (!isTauri) return;
  const { exit } = await import("@tauri-apps/plugin-process");
  await exit(0);
}
