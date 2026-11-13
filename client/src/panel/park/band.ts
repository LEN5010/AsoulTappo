// What each park page puts in the coral band (ParkBand): the host sticker, the page's timer and a quiet info key.
// A section registers its entry while it is mounted; ParkPage shows the entry of the page picked. The sections are
// kept alive, so a page that is not shown keeps its entry and the band swaps at once on a page turn.
import { computed, onBeforeUnmount, ref, shallowReactive, type ComputedRef } from "vue";

export type ParkTab = "coin" | "scratch" | "race" | "lottery";

/** The park page shown. A section may set it to send the player to another page. */
export const parkTab = ref<ParkTab>("coin");

export interface BandEntry {
  /** Image URL of the host standing behind the sheet. */
  host?: string;
  /** "token" for a round picture (a tuanzi): smaller, standing on the sheet's edge. A sticker of 阿草 by default. */
  hostKind?: "sticker" | "token";
  timer?: { label: string; time?: string };
  info?: { label: string; open: () => void };
}

const entries = shallowReactive(new Map<ParkTab, ComputedRef<BandEntry>>());

/** Registers [tab]'s band entry for as long as the calling component lives. Call from setup. */
export function useBand(tab: ParkTab, entry: () => BandEntry): void {
  const live = computed(entry);
  entries.set(tab, live);
  onBeforeUnmount(() => {
    if (entries.get(tab) === live) entries.delete(tab);
  });
}

/** The entry [tab] has registered, or an empty one. */
export function bandOf(tab: ParkTab): BandEntry {
  return entries.get(tab)?.value ?? {};
}

// ---- a host shown for a moment over every page's own (today's free coin: 阿草 takes it)
export const flashedHost = ref("");
let flashTimer: ReturnType<typeof setTimeout> | undefined;

export function flashHost(url: string, ms: number): void {
  clearTimeout(flashTimer);
  flashedHost.value = url;
  flashTimer = setTimeout(() => (flashedHost.value = ""), ms);
}

export function clearFlash(): void {
  clearTimeout(flashTimer);
  flashedHost.value = "";
}
