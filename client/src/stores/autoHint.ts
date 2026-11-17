// The server counts this save's input as automatic (an auto-clicker, a macro; `autoInput` in its status): the pet
// says so over its head, once a day. The bubble stays until the player opens the note behind it (pet/AutoInputNote.vue)
// and closes that.
import { ref } from "vue";
import { dayOf } from "../nudge";

const SEEN_KEY = "asoultappo.autoInputSeen.v1";

/** Whether the bubble is up, and whether the player has opened the note behind it. */
export const autoHint = ref(false);
export const autoNote = ref(false);
/** The note's paper, for placing it over the pet. */
export const AUTO_NOTE_WIDTH = 300;
export const AUTO_NOTE_HEIGHT = 200;

function seenDay(): string {
  try {
    return localStorage.getItem(SEEN_KEY) ?? "";
  } catch {
    return "";
  }
}

/** Takes the status's `autoInput` (seconds left, missing on older servers): puts the bubble up unless the note was closed today. */
export function noteAutoInput(seconds: number | undefined, now = Date.now()): void {
  if (!seconds || autoHint.value || seenDay() === dayOf(now)) return;
  autoHint.value = true;
}

export function openAutoNote(): void {
  if (autoHint.value) autoNote.value = true;
}

/** The player closed the note: the bubble goes with it and stays away for the day. */
export function closeAutoHint(now = Date.now()): void {
  autoHint.value = false;
  autoNote.value = false;
  try {
    localStorage.setItem(SEEN_KEY, dayOf(now));
  } catch {
    // Storage blocked: the bubble comes back with the next status that says so.
  }
}
