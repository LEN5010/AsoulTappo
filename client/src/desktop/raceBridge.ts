// The race's own window in the app: it keeps the settings in step with the desk's (the prices and odds are in the
// local storage the windows share, stores/economy.ts) and asks the desk for the race (stores/park.ts, parkTry). It
// loads none of the desk's network stores.
import type { Settings } from "../stores/settings";
import { syncSettings } from "./settingsSync";
import { requestDesktop } from "./transport";

export async function initRaceWindow(): Promise<() => void> {
  const synced = await syncSettings();
  const initial = await requestDesktop<{ settings: Settings }>("raceSync");
  synced.apply(initial.settings);
  return synced.stop;
}
