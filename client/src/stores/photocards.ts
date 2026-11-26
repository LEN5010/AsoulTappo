// The save's photocards (src/photocards.ts) and the boxes being opened (server/app/photocards.py), by series.
// A box is decided, charged and credited when it is bought; opening it only shows what came. The server hands an
// unopened box of a series back at no charge until it is told the last bag was opened, so buying again after a lost
// answer never pays twice. Each series has its own box on the table. How many bags are open is kept on this device: an
// opening broken off goes on where it was. What unopened bags hold is kept out of what the pages show (photoView).
//
// Requests go through the park's request path (stores/park.ts), so the panel's are relayed to the desk window. Every
// request belongs to a session, raised when the save or server changes: an answer from an earlier one changes nothing.
import { computed, ref, shallowReactive, shallowRef, watch } from "vue";
import { STANDALONE } from "../edition";
import { toHttpBase } from "../net/protocol";
import { photoItem, photoItems, photoItemsOf, photoSeries } from "../photocards";
import { economy, type PhotocardConfig } from "./economy";
import { parkTry, type ParkError } from "./park";
import { loadEconomy, status } from "./player";
import { settings } from "./settings";

/** A bag's card: `new` the first time, `shards` what a repeat turned into, `spare` a signed repeat put by to trade. */
export interface PhotocardPull { item: string; new?: boolean; shards?: number; spare?: boolean }
export interface PhotocardBox {
  id: number;
  /** Unix seconds. */
  ts: number;
  /** What it cost. */
  price: number;
  /** In the order they are opened. */
  cards: PhotocardPull[];
  /** The box completed the signed cards: the repeats put by before it turned into shards. */
  settled?: PhotocardSettled;
}
export interface PhotocardSettled { cards: number; shards: number }
/** The save's photocards of one series. */
export interface PhotocardSave {
  owned: string[];
  /** Boxes left to buy on the state's day; 0 for a series that is not sold. */
  left: number;
  /** Boxes bought in all. */
  boxes: number;
  /** Boxes since the last one with a signed card; 0 once the save holds every signed card. */
  dry: number;
  /** Signed repeats put by. */
  spare: number;
  /** The box not opened to the end yet. */
  box: PhotocardBox | null;
}
export interface PhotocardState {
  /** The China day `left` counts for. */
  day: string;
  /** Every series the server knows by id, on the shelf or not. */
  series: Record<string, PhotocardSave>;
}
/** What buying handed over: the box bought, or the one handed back. A server from before receipts sends none. */
export interface PhotocardReceipt { series: string; box: PhotocardBox }
interface Answer { photocards: PhotocardState; swapped?: string; settled?: PhotocardSettled; receipt?: PhotocardReceipt }

/** A series as the pages show it: what bags left to open hold is not in it. */
export interface PhotoView {
  series: string;
  /** null while the series is not on the shelf. */
  cfg: PhotocardConfig | null;
  /** The server's latest state of it; null before the first load. */
  save: PhotocardSave | null;
  /** The box on the table: the one being opened, or the one just opened until it is put away. */
  box: PhotocardBox | null;
  /** Bags of the box on the table opened so far. */
  opened: number;
  /** The box on the table has bags left to open. */
  opening: boolean;
  owned: ReadonlySet<string>;
  /** Signed repeats put by. */
  spare: number;
  /** The save holds every signed card of the series. */
  signsWhole: boolean;
  /**
   * Within how many boxes a signed card comes for certain, counting the next one. null once there is none to come, and
   * while bags are left to open: the count already knows what they hold.
   */
  pity: number | null;
  /** A trade can be made now. Not with bags left to open: one of them may hold the card chosen. */
  canSwap: boolean;
}

const OPENED_KEY = "asoultappo.photocards.opened.v1";
/** Boxes remembered for the bags opened, those the server has not heard the end of. */
const KEEP = 10;
/** Waits before the end of a box is told again. */
const BACKOFF_MS = [1000, 3000, 8000, 20000];
const OFFLINE = "无法连接服务器";
const OPENED_ELSEWHERE = "这盒已在其他设备开完";

/** The server's latest state; null before the first load. */
export const photoState = shallowRef<PhotocardState | null>(null);
/** The series a box is being bought of, one at a time; "" when none is. */
export const photoBuying = ref("");
export const photoSwapping = ref(false);
/** Why the latest request failed; "" after one that worked. */
export const photoError = ref("");
/** The server answered that it has no photocards. */
const refused = ref(false);

/** The server's shelf; empty without photocards. */
const offered = computed<PhotocardConfig[]>(() => {
  const shelf = economy.value?.photocards;
  return !STANDALONE && Array.isArray(shelf) ? shelf : [];
});
/** The boxes on the shelf, in its order; series whose cards this build lacks are left out. */
export const photoShelf = computed(() => offered.value.filter((c) => photoItems(c.series).length > 0));
/** Whether the shelf has something to show. */
export const photoOn = computed(() => photoShelf.value.length > 0 && !refused.value);
/** The series that have an album: those on the shelf, then those off it that the save has a card of. */
export const photoAlbums = computed(() => {
  if (!offered.value.length || refused.value) return [];
  const shelf = photoShelf.value.map((c) => c.series);
  const kept = photoSeries.filter(({ id }) => !shelf.includes(id) && photoView(id).owned.size > 0);
  return [...shelf, ...kept.map(({ id }) => id)];
});

/** A box on the table and how many of its bags are open. */
interface Table { box: PhotocardBox; opened: number }
/** By series. */
const tables = shallowReactive(new Map<string, Table>());
/** The series' box on the table while it has bags left to open. */
function waiting(series: string): Table | undefined {
  const table = tables.get(series);
  return table && table.opened < table.box.cards.length ? table : undefined;
}

function view(series: string): PhotoView {
  const cfg = photoShelf.value.find((c) => c.series === series) ?? null;
  const save = photoState.value?.series[series] ?? null;
  const { box = null, opened = 0 } = tables.get(series) ?? {};
  const opening = !!waiting(series);
  const owned = new Set(save?.owned);
  let spare = save?.spare ?? 0;
  if (box && opening) {
    for (const c of box.cards.slice(opened)) {
      if (c.new) owned.delete(c.item);
      if (c.spare) spare--;
    }
    // Paid out with this box, which has not told so yet.
    spare += box.settled?.cards ?? 0;
  }
  spare = Math.max(0, spare);
  const signsWhole = photoItemsOf(series, "sign").every((i) => owned.has(i.id));
  const lacking = !opening && !signsWhole;
  return {
    series, cfg, save, box, opened, opening, owned, spare, signsWhole,
    pity: cfg && save && lacking ? Math.max(1, cfg.signPity - save.dry) : null,
    canSwap: !!cfg && lacking && spare >= cfg.swap,
  };
}
/** One for each series of this build. */
const views = new Map(photoSeries.map(({ id }) => [id, computed(() => view(id))]));
/** What a series this build lacks shows. */
const NOTHING: Omit<PhotoView, "series"> = {
  cfg: null, save: null, box: null, opened: 0, opening: false, owned: new Set(), spare: 0, signsWhole: false,
  pity: null, canSwap: false,
};
/** The series as the pages show it. Read in a computed, it is followed. */
export const photoView = (series: string): PhotoView => views.get(series)?.value ?? { series, ...NOTHING };

const chinaDay = (ms: number) => new Date(ms + 8 * 3600_000).toISOString().slice(0, 10);
/** Boxes of the series to buy today yet; null before the first load. One waiting to be opened takes none. */
export function photoLeft(series: string, now = Date.now()): number | null {
  const s = photoState.value;
  const { cfg, save } = photoView(series);
  if (!s || !save) return null;
  const daily = cfg?.daily ?? 0;
  // The day the server counted is over: its successor's are all left.
  return s.day < chinaDay(now) ? daily : Math.min(save.left, daily);
}

/** The save the state belongs to: server and player. */
const identity = computed(() => `${toHttpBase(settings.serverUrl)}|${status.value?.player ?? ""}`);
const boxKey = (id: number) => `${identity.value}|${id}`;

let session = 0;
/** Requests sent, and the number of the latest one whose answer was taken: an older answer never replaces a newer. */
let asked = 0;
let taken = 0;
/** The ends of boxes being told to the server, by box. */
const finishing = new Map<number, Promise<boolean>>();
/** The store has been asked for something: it follows the save from then on. */
let used = false;

function readOpened(): [string, number][] {
  try {
    const raw = JSON.parse(localStorage.getItem(OPENED_KEY) ?? "[]") as unknown;
    if (!Array.isArray(raw)) return [];
    return raw.filter((e): e is [string, number] =>
      Array.isArray(e) && typeof e[0] === "string" && Number.isInteger(e[1]));
  } catch {
    return [];
  }
}
const openedOf = (id: number) => readOpened().find(([key]) => key === boxKey(id))?.[1] ?? 0;
/** Remembers [n] bags of the box as opened; null forgets the box. */
function saveOpened(id: number, n: number | null): void {
  const key = boxKey(id);
  const others = readOpened().filter(([k]) => k !== key);
  try {
    localStorage.setItem(OPENED_KEY, JSON.stringify((n === null ? others : [...others, [key, n]]).slice(-KEEP)));
  } catch {
    /* storage unavailable: kept for this window only */
  }
}

const lost = (e: ParkError) => (e.status === 0 && e.code !== "stale" && e.code !== "bad_path") || e.status >= 500;
const messageOf = (e: ParkError) => (e.status === 0 ? OFFLINE : e.message);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type Reply = { ok: true; data: Answer } | { ok: false; error: ParkError };
/** A photocard request; its state is taken before it resolves. null when the save changed meanwhile. */
async function request(method: "GET" | "POST", path: string, body?: unknown): Promise<Reply | null> {
  const mine = session;
  const n = ++asked;
  const r = await parkTry<Answer>(method, `/api/photocards${path}`, body);
  if (mine !== session || (!r.ok && r.error.code === "stale")) return null;
  if (r.ok) {
    if (!r.data?.photocards?.series) {
      return { ok: false, error: { status: 0, code: "bad_answer", message: "", detail: {} } };
    }
    refused.value = false;
    if (n > taken) {
      taken = n;
      take(r.data.photocards);
    }
    return r;
  }
  const { code, status: http } = r.error;
  // A server without photocards, or from before them.
  if (code === "no_photocards" || (http === 404 && code === "http_error")) refused.value = true;
  return r;
}

function take(state: PhotocardState): void {
  photoState.value = state;
  for (const { id: series } of photoSeries) {
    const box = state.series[series]?.box;
    if (!box) {
      // Opened to the end elsewhere (another device of the save): what is on the table here is over too.
      if (waiting(series)) tables.delete(series);
    } else if (openedHere(series, box)) {
      // The server has not heard of it.
      void finish(box.id);
    } else if (tables.get(series)?.box.id !== box.id) {
      tables.set(series, { box, opened: openedOf(box.id) });
    }
  }
}

/** Every bag of the series' [box] was opened on this device. */
function openedHere(series: string, box: PhotocardBox): boolean {
  const table = tables.get(series);
  return (table?.box.id === box.id ? table.opened : openedOf(box.id)) >= box.cards.length;
}

/** Tells the server the box was opened to the end, again while there is no answer. false when it could not be told. */
function finish(id: number): Promise<boolean> {
  const going = finishing.get(id);
  if (going) return going;
  const mine = session;
  const tell = async (): Promise<boolean> => {
    for (let tries = 0; ; tries++) {
      const r = await request("POST", "/open", { box: id });
      if (!r) return false;
      // no_box: the save was reset meanwhile, so there is nothing left to tell.
      if (r.ok || r.error.code === "no_box") {
        saveOpened(id, null);
        return true;
      }
      const wait = lost(r.error) ? BACKOFF_MS[tries] : undefined;
      if (wait === undefined) return false;
      await sleep(wait);
      if (mine !== session) return false;
    }
  };
  const done = tell().finally(() => {
    if (finishing.get(id) === done) finishing.delete(id);
  });
  finishing.set(id, done);
  return done;
}

/** Loads the save's photocards. false when the request failed (photoError says why). */
export async function loadPhotocards(): Promise<boolean> {
  used = true;
  if (!offered.value.length) return false;
  const r = await request("GET", "");
  if (!r) return false;
  photoError.value = r.ok ? "" : messageOf(r.error);
  return r.ok;
}

/**
 * Buys a box of the series and puts it on the table, or puts back the one waiting to be opened. null when there is none
 * to open (photoError says why).
 */
export async function buyPhotoBox(series: string): Promise<PhotocardBox | null> {
  used = true;
  const here = waiting(series);
  if (here) return here.box;
  if (STANDALONE || photoBuying.value || !views.has(series)) return null;
  photoBuying.value = series;
  photoError.value = "";
  const mine = session;
  try {
    // A box opened to the end here that the server has not heard of would be handed back again.
    if (!photoState.value && !(await loadPhotocards())) return null;
    const before = photoState.value?.series[series]?.box;
    if (before && openedHere(series, before) && !(await finish(before.id))) {
      if (mine === session) photoError.value = OFFLINE;
      return null;
    }
    if (mine !== session) return null;
    // What the shelf says it costs: a server that asks for another price by now refuses.
    const price = photoView(series).cfg?.price;
    const r = await request("POST", "/buy", { series, price });
    if (!r) return null;
    if (r.ok) return await settle(series, r.data.receipt);
    const message = messageOf(r.error);
    if (lost(r.error)) {
      // No answer: the box may have been bought. A load finds it.
      const found = await request("GET", "");
      if (!found) return null;
      const bought = waiting(series);
      if (bought) return bought.box;
    } else {
      // What it was refused for may be news here: the price, or the boxes left.
      if (r.error.code === "price_changed") void loadEconomy();
      void request("GET", "");
    }
    photoError.value = message;
    return null;
  } finally {
    if (mine === session) photoBuying.value = "";
  }
}

/**
 * The box a purchase handed over, on the table. The state taken may not show it: an answer sent later came back first,
 * or another device opened it meanwhile. Then the state is loaded once more; the box is opened elsewhere when that one
 * lacks it too, and the receipt's box is taken where it cannot be loaded.
 */
async function settle(series: string, receipt: PhotocardReceipt | undefined): Promise<PhotocardBox | null> {
  const bought = receipt?.series === series ? receipt.box : undefined;
  const confirmed = () => {
    const box = waiting(series)?.box;
    return box && (!bought || box.id === bought.id) ? box : null;
  };
  const now = confirmed();
  if (now) return now;
  const found = await request("GET", "");
  if (!found) return null;
  const box = confirmed();
  if (box) return box;
  if (found.ok) {
    if (bought) photoError.value = OPENED_ELSEWHERE;
    return null;
  }
  // Whether it was opened elsewhere cannot be told: the box bought is opened here.
  if (bought && !waiting(series)) tables.set(series, { box: bought, opened: openedOf(bought.id) });
  const taken = confirmed();
  if (!taken) photoError.value = messageOf(found.error);
  return taken;
}

/**
 * [n] bags of the series' box [id] are open by now (never fewer than before). The last one ends the box. Nothing happens
 * once another box lies on the table: this one was opened to the end elsewhere.
 */
export function openPhotoBags(series: string, id: number, n: number): void {
  const table = tables.get(series);
  if (table?.box.id !== id) return;
  const { box } = table;
  const opened = Math.min(n, box.cards.length);
  if (opened <= table.opened) return;
  tables.set(series, { box, opened });
  saveOpened(box.id, opened);
  if (opened === box.cards.length) void finish(box.id);
}

/** Puts the series' opened box away; one with bags left stays. */
export function putPhotoBoxAway(series: string): void {
  if (!waiting(series)) tables.delete(series);
}

/** Trades signed repeats of its series for the signed card [item]. null when refused (photoError says why). */
export async function swapPhoto(item: string): Promise<{ item: string; settled?: PhotocardSettled } | null> {
  const series = photoItem(item)?.series ?? "";
  const { canSwap, owned } = photoView(series);
  if (STANDALONE || photoSwapping.value || !canSwap || owned.has(item)) return null;
  photoSwapping.value = true;
  photoError.value = "";
  const mine = session;
  try {
    const r = await request("POST", "/swap", { item });
    if (!r) return null;
    if (r.ok) return { item, ...(r.data.settled ? { settled: r.data.settled } : {}) };
    const message = messageOf(r.error);
    // No answer: the trade may have been made. A load finds the card.
    if (lost(r.error)) {
      const found = await request("GET", "");
      if (!found) return null;
      if (found.ok && found.data.photocards.series[series]?.owned.includes(item)) return { item };
    }
    photoError.value = message;
    return null;
  } finally {
    if (mine === session) photoSwapping.value = false;
  }
}

/** Another save or server: nothing of the last one stays. */
export function resetPhotocards(): void {
  session++;
  finishing.clear();
  photoState.value = null;
  tables.clear();
  photoBuying.value = "";
  photoSwapping.value = false;
  photoError.value = "";
  refused.value = false;
}

watch(identity, () => {
  resetPhotocards();
  if (used && status.value?.player) void loadPhotocards();
});
/** What the server's answer depends on of the shelf. */
const sales = (shelf: PhotocardConfig[]) => JSON.stringify(shelf.map((c) => [c.series, c.daily]));
// Boxes that come on sale or go off it while the client runs, or a server that gained them after it refused.
watch(offered, (now, before) => {
  refused.value = false;
  if (used && status.value?.player && (!photoState.value || sales(now) !== sales(before))) void loadPhotocards();
});
