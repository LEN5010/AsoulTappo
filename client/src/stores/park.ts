// The park (docs: protocol/PROTOCOL.md 游乐园): its state, the one way every park game reaches the server, and the
// server-wide news of big wins. Requests run in the desk window like every other; the panel relays them there
// (desktop/bridge.ts) and gets the answer back with the server's error code intact.
import { computed, ref, watch } from "vue";
import { ApiError, type ParkState, type ParkStatus, type PlayerStatus } from "../net/api";
import { toHttpBase } from "../net/protocol";
import { isPanelWindow } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { rememberNews, unseenNews } from "../parkNews";
import { account, attempt, freshItems, reloadCollection, saveCode, status } from "./player";
import { settings } from "./settings";

export type ParkMethod = "GET" | "POST";

/** A refused or failed park request. `status` is 0 when nothing came back from the server. */
export interface ParkError { status: number; code: string; message: string; detail: Record<string, unknown> }
export type ParkReply<T> = { ok: true; data: T } | { ok: false; error: ParkError };

/** The save's park, once loaded (loadPark); null before that, after a save or server switch, and without a park. */
export const park = ref<ParkState | null>(null);
/** Why the latest parkCall failed; null after one that worked. */
export const parkError = ref<ParkError | null>(null);
/** The status says this server has no park. Unknown (false) while there is no status yet. */
export const noPark = computed(() => !!status.value && !status.value.park);

export function isParkState(v: unknown): v is ParkState {
  return !!v && typeof v === "object" && "unlocked" in v && typeof (v as ParkState).coins === "number";
}
const isParkStatus = (v: unknown): v is ParkStatus =>
  !!v && typeof v === "object" && Array.isArray((v as ParkStatus).news) && typeof (v as ParkStatus).coins === "number";

/**
 * What an answer of the park holds: a player status when it has `player` and `shards`, and the park's state when
 * it is one (GET /api/park) or carries one as `park`. A status keeps its own `park` ({coins, news}): the state's
 * coins with the news it had before. The answer's own fields (a prize, a card) stay out of the status: with a
 * previous status, only the keys it has are kept (the server's status keys depend only on its manifest).
 */
export function splitParkResult(r: unknown, prev: PlayerStatus | null): { status: PlayerStatus | null; park: ParkState | null } {
  if (!r || typeof r !== "object") return { status: null, park: null };
  const o = r as Record<string, unknown>;
  const isStatus = "player" in o && "shards" in o;
  if (!isStatus) return { status: null, park: isParkState(o) ? o : isParkState(o.park) ? o.park : null };
  const { park: p, ...rest } = o;
  const state = isParkState(p) ? p : null;
  const own = state ? { coins: state.coins, news: prev?.park?.news ?? [] } : isParkStatus(p) ? p : prev?.park;
  const next = (prev ? Object.fromEntries(Object.entries(rest).filter(([k]) => k in prev)) : rest) as unknown as PlayerStatus;
  if (own) next.park = own;
  return { status: next, park: state };
}

function apply(r: unknown): void {
  const split = splitParkResult(r, status.value);
  if (split.status) status.value = split.status;
  if (!split.park) return;
  park.value = split.park;
  const s = status.value;
  if (!split.status && s?.park && s.park.coins !== split.park.coins) status.value = { ...s, park: { ...s.park, coins: split.park.coins } };
}

function toParkError(e: unknown): ParkError {
  if (e instanceof ApiError) return { status: e.status, code: e.code, message: e.message, detail: { ...e.detail } };
  return { status: 0, code: "offline", message: "无法连接服务器", detail: {} };
}

/** Desk window only (the panel goes through parkTry): sends the request and applies its answer here. */
export async function parkRequest<T>(method: ParkMethod, path: string, body?: unknown): Promise<ParkReply<T>> {
  const r = await attempt((api) => api.park<T>(method, path, body));
  if (!r) return { ok: false, error: { status: 0, code: "stale", message: "", detail: {} } };
  if (!r.ok) return { ok: false, error: toParkError(r.error) };
  apply(r.value);
  // A prize that is an item (a scratch card's emote, skin or big hidden card) reaches the collection.
  const item = (r.value as { prize?: { item?: unknown } } | null)?.prize?.item;
  if (typeof item === "string" && item) {
    freshItems.add(item);
    await reloadCollection();
  }
  return { ok: true, data: r.value };
}

/**
 * Any request of the park or redeem codes (paths under /api/park or /api/redeem), from either window. The answer's
 * status and park state are applied before it resolves; a failure resolves with the error, never rejects.
 */
export async function parkTry<T>(method: ParkMethod, path: string, body?: unknown): Promise<ParkReply<T>> {
  if (!isPanelWindow) return parkRequest<T>(method, path, body);
  let reply: ParkReply<T>;
  try {
    reply = await requestDesktop<ParkReply<T>>("park", method, path, body);
  } catch (e) {
    return { ok: false, error: { status: 0, code: "desktop", message: e instanceof Error ? e.message : String(e), detail: {} } };
  }
  if (reply.ok) apply(reply.data);
  return reply;
}

/** parkTry for a single caller: the answer, or null with the reason in parkError. */
export async function parkCall<T>(method: ParkMethod, path: string, body?: unknown): Promise<T | null> {
  const r = await parkTry<T>(method, path, body);
  parkError.value = r.ok ? null : r.error;
  return r.ok ? r.data : null;
}

/** Loads the save's park; a server whose status has no park is not asked. */
export async function loadPark(): Promise<ParkState | null> {
  if (noPark.value) {
    park.value = null;
    return null;
  }
  return parkCall<ParkState>("GET", "/api/park");
}

/** Buys [count] coins with shards. false when refused (parkError says why). */
export async function buyCoins(count: number): Promise<boolean> {
  return (await parkCall<PlayerStatus>("POST", "/api/park/coins", { count })) !== null;
}

let gifting: Promise<number | null> | null = null;
/** Takes today's free coin: the coins given now (0 when already taken today), or null when the request failed. */
export function claimGift(): Promise<number | null> {
  gifting ??= parkCall<{ gift: number }>("POST", "/api/park/gift")
    .then((r) => (r ? r.gift : null))
    .finally(() => { gifting = null; });
  return gifting;
}

// ---------------------------------------------------------------- the desk keeps the state current
if (!isPanelWindow) {
  // Another save or server: its park is loaded afresh.
  watch(() => [settings.serverUrl, saveCode.value, account.value?.token] as const, () => { park.value = null; }, { flush: "sync" });
  watch(() => status.value?.park?.coins, (coins) => {
    if (status.value && !status.value.park) park.value = null;
    // Coins changed elsewhere (a race refund, another device): the rest of the state may have too.
    else if (park.value && coins !== undefined && coins !== park.value.coins) {
      park.value = { ...park.value, coins };
      void loadPark();
    }
  });
}

// ---------------------------------------------------------------- news
// Ids already shown, by server. The desk's pet shows the rest (pet/ParkNewsBubble.vue) and marks them.
const SEEN_KEY = "asoultappo.parkNews.v1";
const SEEN_SERVERS = 5;

function loadSeen(): Record<string, number[]> {
  try {
    const raw = JSON.parse(localStorage.getItem(SEEN_KEY) ?? "{}");
    return raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  } catch {
    return {};
  }
}
const seenByServer = ref<Record<string, number[]>>(loadSeen());
const newsServer = computed(() => toHttpBase(settings.serverUrl));
const seen = computed(() => new Set(seenByServer.value[newsServer.value] ?? []));

/** News in the latest status this device has not shown yet, oldest first. */
export const unseenParkNews = computed(() => unseenNews(status.value?.park?.news, seen.value));

export function markNewsSeen(ids: number[]): void {
  if (!ids.length) return;
  const key = newsServer.value;
  const { [key]: mine = [], ...others } = seenByServer.value;
  // The current server goes last; the oldest others drop off.
  const kept = Object.entries(others).slice(-(SEEN_SERVERS - 1));
  const next = { ...Object.fromEntries(kept), [key]: rememberNews(mine, ids) };
  seenByServer.value = next;
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: shown again after a restart, if still in the news */
  }
}
