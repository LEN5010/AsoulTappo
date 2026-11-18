// The server counts this save's input as automatic (an auto-clicker, a macro; `autoInput` in its status): the pet
// says so over its head, once a day. The bubble stays until the player opens the note behind it (pet/AutoInputNote.vue)
// and closes that. A save that goes on is given cooldowns (`autoStrikes`, how many today): each new one puts the
// bubble up again.
import { ref } from "vue";
import { dayOf } from "../nudge";

const SEEN_KEY = "asoultappo.autoInputSeen.v1";

/** Whether the bubble is up, and whether the player has opened the note behind it. */
export const autoHint = ref(false);
export const autoNote = ref(false);
/** Today's cooldowns for going on, as of the last status. */
export const autoStrikes = ref(0);
let strikeDay = "";
/** The note's paper, for placing it over the pet. */
export const AUTO_NOTE_WIDTH = 300;
export const AUTO_NOTE_HEIGHT = 200;

/** The day the note was last closed and the strikes it was closed at, stored as `<day>` or `<day>|<strikes>`. */
function seen(): { day: string; strikes: number } {
  let kept = "";
  try {
    kept = localStorage.getItem(SEEN_KEY) ?? "";
  } catch {
    // Storage blocked: nothing was seen.
  }
  const [day, strikes] = kept.split("|");
  return { day, strikes: Number(strikes) || 0 };
}

/**
 * Takes the status's `autoInput` (seconds left, missing on older servers) and `autoStrikes`: puts the bubble up unless
 * the note was closed today with as many strikes.
 */
export function noteAutoInput(seconds: number | undefined, strikes = 0, now = Date.now()): void {
  if (!seconds) return;
  const today = dayOf(now);
  autoStrikes.value = autoHint.value && strikeDay === today ? Math.max(autoStrikes.value, strikes) : strikes;
  strikeDay = today;
  if (autoHint.value) return;
  const was = seen();
  if (was.day === today && strikes <= was.strikes) return;
  autoHint.value = true;
}

export function openAutoNote(): void {
  if (autoHint.value) autoNote.value = true;
}

/** The player closed the note: the bubble goes with it and stays away for the day, or until the next strike. */
export function closeAutoHint(now = Date.now()): void {
  autoHint.value = false;
  autoNote.value = false;
  const today = dayOf(now);
  const strikes = strikeDay === today ? autoStrikes.value : 0;
  try {
    localStorage.setItem(SEEN_KEY, `${today}|${strikes}`);
  } catch {
    // Storage blocked: the bubble comes back with the next status that says so.
  }
}
