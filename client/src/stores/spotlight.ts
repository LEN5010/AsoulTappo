// The launch spotlight: a release's new skins, shown once per device when the panel opens.
//
// It is written nowhere but in the skin list (scripts/asset_catalog.py SKINS): the skins sharing the newest `since`
// are the spotlight, titled with their series. Shipping skins with a later `since` makes the next one; older batches
// never show again, and a fresh install sees the newest batch once. Closing it is remembered with the server
// announcements (`skins:<since>` in the same read list), so a test build of the release shows it too.
import { computed } from "vue";
import { skinSeries } from "../characters";
import { manifest } from "../manifest";
import { compareVersions } from "../semver";
import { noticeSeen, readNotice, updateDialogOpen, unreadNotice } from "./update";

export interface Spotlight { id: string; title: string; skins: string[] }

export function spotlightOf(skins: readonly { name: string; since?: string }[]): Spotlight | null {
  const newest = skins.reduce<string | undefined>(
    (top, s) => (s.since && (!top || (compareVersions(s.since, top) ?? 0) > 0) ? s.since : top), undefined);
  if (!newest) return null;
  const batch = skins.filter((s) => s.since && compareVersions(s.since, newest) === 0).map((s) => s.name);
  return { id: `skins:${newest}`, title: skinSeries(batch[0]!), skins: batch };
}

export const spotlight = spotlightOf(manifest.skins);
/** Not closed on this device yet: the update reward waits for it. */
export const spotlightUnread = computed(() => !!spotlight && !noticeSeen(spotlight.id));
/** Its turn: after the update dialog and the server announcements. */
export const spotlightShown = computed(() => spotlightUnread.value && !updateDialogOpen.value && !unreadNotice.value);
export const readSpotlight = () => { if (spotlight) readNotice(spotlight.id); };
