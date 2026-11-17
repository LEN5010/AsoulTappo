// The server counts this save's input as automatic (an auto-clicker, a macro; `autoInput` in its status): the pet
// says so over its head, once a day, and the note stays until the player closes it.
import { ref } from "vue";
import { dayOf } from "../nudge";

const SEEN_KEY = "asoultappo.autoInputSeen.v1";

/** Whether the note is up. */
export const autoHint = ref(false);

function seenDay(): string {
  try {
    return localStorage.getItem(SEEN_KEY) ?? "";
  } catch {
    return "";
  }
}

/** Takes the status's `autoInput` (seconds left, missing on older servers): puts the note up unless it was closed today. */
export function noteAutoInput(seconds: number | undefined, now = Date.now()): void {
  if (!seconds || autoHint.value || seenDay() === dayOf(now)) return;
  autoHint.value = true;
}

export function closeAutoHint(now = Date.now()): void {
  autoHint.value = false;
  try {
    localStorage.setItem(SEEN_KEY, dayOf(now));
  } catch {
    // Storage blocked: the note comes back with the next status that says so.
  }
}
