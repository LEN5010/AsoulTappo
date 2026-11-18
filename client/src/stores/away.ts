// The status this desk shows its room: the chosen one (settings.status), or "away" by itself after a while without
// input, until the next input. Desk window only: it hears the input and holds the room's connection.
import { computed, ref } from "vue";
import { AWAY_KEEPS, AwayClock } from "../away";
import type { InputEvent } from "../composables/tauri";
import { settings } from "./settings";

const TICK_MS = 15_000;

const idle = ref(false);
let clock = new AwayClock(Date.now());

/** What the room is told: a `ROOM_STATUSES` id, "" for none. */
export const shownStatus = computed(() => (idle.value && !AWAY_KEEPS.has(settings.status) ? "away" : settings.status));

/** Input from the hook. A press other software sent (an auto-clicker left running) does not bring the member back. */
export function noteAwayInput(e: InputEvent): void {
  if ("injected" in e && e.injected) return;
  clock.input(Date.now());
  if (idle.value) idle.value = false;
}

/** Starts watching for a stretch without input. Returns the stop. */
export function startAway(): () => void {
  clock = new AwayClock(Date.now());
  idle.value = false;
  const timer = setInterval(() => { idle.value = clock.away(Date.now()); }, TICK_MS);
  return () => {
    clearInterval(timer);
    idle.value = false;
  };
}
