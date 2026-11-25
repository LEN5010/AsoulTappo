// The photocards' page: which series is on show, what lies over it, and the way from the key to an opened box. The parts
// of it stand in different places of the resonance page (the stage, the bar, the overlays), so they meet here.
import { computed, ref, shallowRef, watch } from "vue";
import { photoSeries, type PhotoItem, type PhotoItemKind } from "../../photocards";
import type { BoxPlace, CardPlace } from "../../photo/place";
import {
  buyPhotoBox, photoBuying, photoError, photoOn, photoShelf, photoView, putPhotoBoxAway, type PhotocardBox, type PhotocardSettled,
} from "../../stores/photocards";

/** Its place among the pools (ui.pool). */
export const PHOTO_POOL = "photocards";

const picked = ref("");
/** The series on sale, in shelf order, then those off it with a box that was not opened to the end and put away. */
export const shelfIds = computed(() => {
  const ids = photoShelf.value.map((c) => c.series);
  return [...ids, ...photoSeries.map((s) => s.id).filter((id) => !ids.includes(id) && photoView(id).box)];
});
/** The series on show: the one picked while it is on the shelf, else the first with a box that waits, else the first. */
export const shopSeries = computed(() => {
  const ids = shelfIds.value;
  return ids.includes(picked.value) ? picked.value : ids.find((id) => photoView(id).opening) ?? ids[0] ?? "";
});
export function pickSeries(id: string): void {
  if (!photoBusy.value) picked.value = id;
}
/** The series the album in the dex was last opened on. */
export const albumSeries = ref("");

export type PhotoOver =
  | { kind: "odds" }
  | { kind: "swap" }
  | { kind: "card"; item: PhotoItem; list: readonly PhotoItem[]; from?: CardPlace; write?: boolean; settled?: PhotocardSettled };
/** The dialog over the page. */
export const photoOver = shallowRef<PhotoOver | null>(null);

/** A box on the table: a new one, one gone on with, or another bought from the result of the last. The first two come
 *  from the shelf. */
export interface PhotoRun { series: string; box: PhotocardBox; start: "new" | "on" | "again" }
export const photoRun = shallowRef<PhotoRun | null>(null);
/** A box is being packed on the shelf and bought meanwhile. */
export const packing = ref(false);
/** The page is in the middle of something: pools and series stay as they are. */
export const photoBusy = computed(() => packing.value || !!photoRun.value);

/** The shelf on the page (PhotoShelf.vue): packs what it shows into the box, and hands the box over to the table. */
export interface ShelfStage {
  pack(): Promise<void>;
  /** Takes everything out again. */
  unpack(): void;
  /** The cards go down behind a box that waits. */
  stow(): Promise<void>;
  /** The box leaves the shelf, for the table that takes it over: where it stands now. */
  hand(): BoxPlace | undefined;
  /** Where a box with bags left stands on the shelf; where a new one will ([fresh]). */
  place(fresh: boolean): BoxPlace | undefined;
  /** The table was cleared; [stands]: the box that stands on the shelf now was put there. */
  back(stands: boolean): void;
}
export const shelfStage = shallowRef<ShelfStage | null>(null);

// ---- the stage under the page (PhotoBackdrop.vue), for a series with a key visual
/** A place on the screen, in client pixels. */
export interface Spot { x: number; y: number; w: number; h: number }
/** The key visual is seen by itself, what lies on it out of the way: the page opens on it, or it was asked for. */
export const poster = ref<"" | "opening" | "look">("");
/** The stage has drawn, or cannot be drawn. */
export const groundUp = ref(false);
/** When the key visual began to come up out of the paper, in performance.now()'s time. */
export const groundRose = ref(0);
/** The kind its lamps light up for. */
export const groundKind = ref<PhotoItemKind | null>(null);
/** Where the box stands, with CSS pixels to a design unit there; null where there is no floor for it. */
export const groundFoot = shallowRef<{ x: number; y: number; css: number } | null>(null);
/** Where the title stands on the page. */
export const groundTitle = shallowRef<Spot | null>(null);
/** The series the page opened on by its key visual since the app started: once each. */
export const opened = new Set<string>();
/** The page of a series with a key visual is come to: the first time it opens on that, unless something lies over it. */
export function openPage(series: string): void {
  if (poster.value || opened.has(series) || photoBusy.value || photoOver.value) return;
  if (globalThis.document?.querySelector("[data-overlay]")) return;
  poster.value = "opening";
}

/** Counts the ways begun from the shelf to the table, and the times they were broken off. */
let way = 0;
/** The way [go] makes over the shelf, or as much of it as there was time for before the shelf was taken away. */
function over(go: (stage: ShelfStage) => Promise<void>): Promise<void> {
  const stage = shelfStage.value;
  if (!stage) return Promise.resolve();
  let off = () => {};
  const gone = new Promise<void>((done) => { off = watch(shelfStage, () => done(), { flush: "sync" }); });
  return Promise.race([go(stage), gone]).finally(() => off());
}
function begin(series: string): number {
  picked.value = series;
  packing.value = true;
  photoError.value = "";
  return ++way;
}
function arrive(run: PhotoRun): void {
  photoRun.value = run;
  packing.value = false;
}

/** Buys a box of the series on show: the shelf packs it while the request is out, then it goes to the table. */
export async function buyOnShelf(): Promise<void> {
  if (photoBusy.value) return;
  const series = shopSeries.value, stage = shelfStage.value, mine = begin(series);
  const packed = over((s) => s.pack());
  const box = await buyPhotoBox(series);
  if (mine !== way) return;
  if (!box) {
    if (shelfStage.value === stage) stage?.unpack();
    packing.value = false;
    return;
  }
  await packed;
  if (mine === way) arrive({ series, box, start: "new" });
}

/** Goes on with the box that waits. */
export async function resumeOnShelf(): Promise<void> {
  const series = shopSeries.value;
  const { box, opening, opened } = photoView(series);
  if (photoBusy.value || !box || !opening) return;
  const mine = begin(series);
  await over((s) => s.stow());
  if (mine === way) arrive({ series, box, start: opened ? "on" : "new" });
}

/** The page is left: what was on its way to the table stops, and a box that was bought waits on the shelf. */
export function breakOff(): void {
  way++;
  packing.value = false;
  poster.value = "";
}
/** The page goes away, or what it sells: nothing of it stays up. */
export function leaveShop(): void {
  breakOff();
  photoOver.value = null;
  photoRun.value = null;
}

/** Another box from the result of the last one; null when it could not be bought (photoError says why). */
export async function buyAnother(): Promise<PhotocardBox | null> {
  const run = photoRun.value;
  if (!run || photoBuying.value) return null;
  const box = await buyPhotoBox(run.series);
  if (box && photoRun.value) photoRun.value = { series: run.series, box, start: "again" };
  return box;
}

/** The table is left: an opened box is put away, one with bags left waits on the shelf. [stands]: as of ShelfStage. */
export function clearTable(stands = false): void {
  const run = photoRun.value;
  if (!run) return;
  putPhotoBoxAway(run.series);
  photoRun.value = null;
  shelfStage.value?.back(stands);
}

const SEEN_KEY = "asoultappo.photocards.seen.v1";
const read = () => { try { return localStorage.getItem(SEEN_KEY) ?? ""; } catch { return SEEN_KEY; } };
const seen = ref(read());
/** Series that came on the shelf since the page was last looked at: the pool's tab says so. */
export const shopFresh = computed(() => photoOn.value && shelfIds.value.some((id) => !seen.value.split(",").includes(id)));
export function markShopSeen(): void {
  const ids = new Set([...seen.value.split(",").filter(Boolean), ...shelfIds.value]);
  const next = [...ids].join();
  if (next === seen.value) return;
  seen.value = next;
  try { localStorage.setItem(SEEN_KEY, next); } catch { /* storage unavailable: for this window only */ }
}
