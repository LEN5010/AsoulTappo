import { computed, reactive, ref, watch } from "vue";
import {
  Api, ActivityReporter, ApiError, newToken,
  type Board, type CheckinMonth, type CheckinResult, type Collection, type Credential, type Drop, type DropHistory, type HistoryDrop, type Loadout, type LoadoutPatch, type MainUser,
  type PlayerStatus, type ResonanceResult, type ScratchCard, type ScratchRevealResult,
} from "../net/api";
import { MAX_BOARD_NICK, MAX_SHOWCASE, toHttpBase, type MemberProfile } from "../net/protocol";
import { trustedOrigin } from "../net/trust";
import { ownsCharacter, ownsEmote } from "../items";
import { plateUnlocked } from "../pet/plates";
import { getCard, memberOf, type Rarity } from "../manifest";
import { settings } from "./settings";
import { economy, economyDue, setEconomy } from "./economy";
import { isPanelWindow } from "../composables/tauri";
import { agreed } from "../legal/consent";
import { requestDesktop } from "../desktop/transport";
import { compareVersions } from "../semver";
import { APP_VERSION } from "../version";

const TOKEN_KEY = "asoultappo.token.v1";

function loadToken(): string {
  try {
    const t = localStorage.getItem(TOKEN_KEY);
    if (t && t.length >= 16) return t;
    const n = newToken();
    localStorage.setItem(TOKEN_KEY, n);
    return n;
  } catch {
    return newToken();
  }
}

export let token = loadToken();
export const saveCode = ref(token);

// ---------------------------------------------------------------- account
// A main-site account signed in on one server. While it is active the save linked to it replaces the guest save.
const ACCOUNT_KEY = "asoultappo.account.v1";
export interface AccountSession { server: string; token: string; user: MainUser }

function loadAccount(): AccountSession | null {
  try {
    const raw = JSON.parse(localStorage.getItem(ACCOUNT_KEY) ?? "null");
    return raw?.token && raw?.server && raw?.user?.id ? raw : null;
  } catch {
    return null;
  }
}
export const account = ref<AccountSession | null>(loadAccount());

/** The account for the selected server, if any. A stored session never counts on an untrusted server. */
export function activeAccount(): AccountSession | null {
  const a = account.value;
  const base = toHttpBase(settings.serverUrl);
  return a && a.server === base && trustedOrigin(base) ? a : null;
}

/** Signs this device into [session] (null signs out). A guest save that now belongs to the account gets replaced. */
export async function setAccount(session: AccountSession | null, retireGuest = false): Promise<AccountSession | null> {
  if (isPanelWindow) {
    account.value = await requestDesktop<AccountSession | null>("setAccount", session, retireGuest);
    if (retireGuest) saveCode.value = loadToken();
    return account.value;
  }
  if (session) localStorage.setItem(ACCOUNT_KEY, JSON.stringify(session));
  else localStorage.removeItem(ACCOUNT_KEY);
  if (retireGuest) {
    const fresh = newToken();
    localStorage.setItem(TOKEN_KEY, fresh);
    saveCode.value = fresh;
  }
  account.value = session;
  return session;
}

// The panel window follows sign-ins and sign-outs made by the desk window (same origin, shared storage).
if (isPanelWindow) {
  window.addEventListener?.("storage", (e) => {
    if (e.key === ACCOUNT_KEY) account.value = loadAccount();
    if (e.key === TOKEN_KEY) saveCode.value = loadToken();
  });
}

/** Picks up a username or email changed on the website. */
export async function refreshAccount(): Promise<void> {
  const a = activeAccount();
  if (!a) return;
  try {
    const { user } = await new Api(() => a.server, () => ({ bearer: a.token })).account();
    if (account.value?.token === a.token && (user.username !== a.user.username || user.email !== a.user.email)) {
      await setAccount({ ...a, user });
    }
  } catch (e) {
    if (e instanceof ApiError && e.code === "account_expired") await setAccount(null);
  }
}

function credential(base: string): Credential {
  const a = account.value;
  return a && a.server === base && trustedOrigin(base) ? { bearer: a.token } : token;
}

export const status = ref<PlayerStatus | null>(null);
export const collection = reactive<Collection>({ owned: {}, recent: [] });
export const online = ref(false);
export const error = ref("");
export const draws = computed(() => {
  const cost = economy.value?.resonance.cost;
  return cost ? Math.floor((status.value?.shards ?? 0) / cost) : 0;
});
const presenceSession = newToken();
let heartbeatBusy = false;

export async function heartbeat(): Promise<void> {
  if (heartbeatBusy) return;
  heartbeatBusy = true;
  const session = current;
  const gen = generation;
  try {
    const result = await serial(session, () => session.api.presence(presenceSession));
    if (session === current && gen === generation) {
      status.value = result;
      online.value = true;
      error.value = "";
      if (loadoutPending) {
        loadoutPending = false;
        void refresh();
      }
      if (economyDue()) void loadEconomy();
    }
  } catch (e) {
    if (session === current && gen === generation) {
      if (!(e instanceof ApiError) || e.status >= 500) online.value = false;
    }
  } finally {
    heartbeatBusy = false;
  }
}

export const shards = computed(() => status.value?.shards ?? 0);
/** Items obtained in this session that the player has not looked at yet. */
export const freshItems = reactive(new Set<string>());

interface Session { api: Api; reporter: ActivityReporter; tail: Promise<unknown> }
/**
 * Runs the session's requests one after another. Nothing reaches the server before the player agrees to the terms
 * (src/legal): a request that comes up before that fails unsent, and a batch of taps stays queued for later.
 */
function serial<T>(session: Session, fn: () => Promise<T>): Promise<T> {
  const next = session.tail.then(() => {
    if (!agreed.value) throw new Error("terms not agreed");
    return fn();
  });
  session.tail = next.catch(() => {});
  return next;
}
const sessions = new Map<string, Session>();
let generation = 0;
let timer: ReturnType<typeof setInterval> | undefined;

function sessionFor(base: string): Session {
  const auth = credential(base);
  const key = `${base}|${typeof auth === "string" ? auth : `account:${auth.bearer}`}`;
  const found = sessions.get(key);
  if (found) return found;
  const api = new Api(() => base, () => auth);
  const session: Session = { api, tail: Promise.resolve(), reporter: new ActivityReporter(async (batch) => {
    const gen = generation;
    const result = await serial(session, () => api.activity(batch));
    if (current === session && gen === generation) {
      status.value = result;
      online.value = true;
      error.value = "";
    }
  }) };
  sessions.set(key, session);
  return session;
}

let current = sessionFor(toHttpBase(settings.serverUrl));

function fail(e: unknown): void {
  // A rejected request (4xx) means the server is reachable; only network / 5xx errors are "offline".
  if (!(e instanceof ApiError) || e.status >= 500) online.value = false;
  error.value = e instanceof ApiError ? e.message : "无法连接服务器";
  if (e instanceof ApiError && e.code === "account_expired") void setAccount(null);
}

/** Run a request on the current session; results of older server selections are dropped (null). */
async function call<T>(fn: (api: Api) => Promise<T>): Promise<T | null> {
  const session = current;
  const gen = generation;
  try {
    const r = await serial(session, () => fn(session.api));
    return session === current && gen === generation ? r : null;
  } catch (e) {
    if (session === current && gen === generation) fail(e);
    return null;
  }
}

/**
 * Like call(), for callers that show their own errors (the park, stores/park.ts): the error comes back instead of
 * going to `error`. Network and 5xx failures still count as offline, and an expired account still signs out. null
 * when the server selection changed meanwhile.
 */
export async function attempt<T>(fn: (api: Api) => Promise<T>): Promise<{ ok: true; value: T } | { ok: false; error: unknown } | null> {
  const session = current;
  const gen = generation;
  try {
    const value = await serial(session, () => fn(session.api));
    return session === current && gen === generation ? { ok: true, value } : null;
  } catch (e) {
    if (session !== current || gen !== generation) return null;
    if (!(e instanceof ApiError) || e.status >= 500) online.value = false;
    if (e instanceof ApiError && e.code === "account_expired") void setAccount(null);
    return { ok: false, error: e };
  }
}

let economyLoad: { generation: number; pending: Promise<void> } | undefined;
/** Asks the current server for its economy (src/stores/economy.ts); failures keep what is cached and retry later. */
export async function loadEconomy(base = toHttpBase(settings.serverUrl)): Promise<void> {
  if (base !== toHttpBase(settings.serverUrl)) return;
  if (isPanelWindow) return requestDesktop("loadEconomy", base).catch(() => {});
  if (economyLoad?.generation === generation) return economyLoad.pending;
  let at = 0;
  const pending = attempt((api) => {
    at = Date.now();
    return api.economy();
  }).then((got) => {
    if (got?.ok) setEconomy(got.value, base, at);
  }).finally(() => {
    if (economyLoad?.pending === pending) economyLoad = undefined;
  });
  economyLoad = { generation, pending };
  return pending;
}

export async function refresh(): Promise<void> {
  const session = current;
  const gen = generation;
  let player: string;
  try {
    const [s, c] = await serial(session, () => Promise.all([session.api.me(), session.api.collection()]));
    if (session !== current || gen !== generation) return;
    player = s.player;
    status.value = s;
    collection.owned = c.owned;
    collection.recent = c.recent;
    online.value = true;
    error.value = "";
  } catch (e) {
    if (session === current && gen === generation) fail(e);
    return;
  }
  void loadEconomy();
  const save = saveKey(toHttpBase(settings.serverUrl), player);
  if (loadoutOwner !== null && loadoutOwner !== save) {
    // Another save: its stored loadout replaces the local one, which the previous save already holds.
    const stored = await call((api) => api.loadout());
    if (session !== current || gen !== generation) return;
    if (!stored) {
      // Nothing is pushed and no owner recorded; the next heartbeat that gets through refreshes again.
      loadoutPending = true;
      return;
    }
    applyLoadout(stored);
    sanitizeLoadout();
    // The board nick and opt-out belong to this device, not to the save: they count as pushed only as the save
    // holds them, and a difference goes to the save now rather than with the next local change.
    const local = localLoadout();
    lastPushed = JSON.stringify({ ...local, nick: stored.nick ?? local.nick, board: stored.board ?? local.board });
    setLoadoutOwner(save);
    if (JSON.stringify(local) !== lastPushed) void pushLoadout();
    return;
  }
  if (loadoutOwner === null) setLoadoutOwner(save); // first run: the local loadout belongs to this save
  sanitizeLoadout();
  void pushLoadout();
}

async function flush(session: Session): Promise<boolean> {
  const gen = generation;
  const ok = await session.reporter.flush();
  if (!ok && session === current && gen === generation) online.value = false;
  return ok;
}

watch(() => [settings.serverUrl, saveCode.value, account.value?.token] as const, ([url, code]) => {
  if (isPanelWindow) return;
  const previous = current;
  token = code;
  generation++;
  current = sessionFor(toHttpBase(url));
  status.value = null;
  collection.owned = {};
  collection.recent = [];
  checkins.value = null;
  scratchCard.value = null;
  freshItems.clear();
  online.value = false;
  error.value = "";
  lastPushed = "";
  loadoutPending = false;
  // Each reporter keeps its original server and batch identity, including retries.
  void flush(previous);
  if (timer) { void refresh(); void heartbeat(); }
}, { flush: "sync" });

/** One tap; `injected` as the input hook said of it (see InputEvent). */
export function countInput(injected?: boolean): void {
  current.reporter.add(1, injected);
}

/** The input guard stopped counting taps until `until` (ms): tell the server now, so the multiplier stops too. */
export function reportCooldown(until: number): void {
  current.reporter.cool(until);
  void flush(current);
}

/** Set while reporting waits for the player to agree to the terms. */
let waiting: (() => void) | undefined;

export function startReporting(everyMs = 20000): void {
  if (timer || waiting) return;
  if (!agreed.value) {
    // Nothing reaches the server before the player agrees to the terms (src/legal); agreeing starts it.
    waiting = watch(agreed, (ok) => {
      if (!ok) return;
      waiting?.();
      waiting = undefined;
      startReporting(everyMs);
    });
    return;
  }
  void refresh().then(heartbeat); // establishes the input and running-time baselines
  timer = setInterval(() => {
    void heartbeat();
    for (const session of sessions.values()) {
      if (session.reporter.due()) void flush(session);
    }
  }, everyMs);
}

export function stopReporting(): void {
  waiting?.();
  waiting = undefined;
  if (timer) clearInterval(timer);
  timer = undefined;
  for (const session of sessions.values()) void flush(session);
}

/**
 * Reloads the status after the room server moved shards (a duel's bets and prize). It waits behind requests already
 * on their way, so an older answer cannot put the previous balance back afterwards.
 */
export async function reloadStatus(): Promise<void> {
  if (isPanelWindow) return;
  const s = await call((api) => api.me());
  if (s) status.value = s;
}

/** Desk window only: loads the collection again after items arrived (the panel gets it with the next sync). */
export async function reloadCollection(): Promise<void> {
  const c = await call((api) => api.collection());
  if (c) {
    collection.owned = c.owned;
    collection.recent = c.recent;
  }
}

export async function resonate(count = 1, banner?: string): Promise<Drop[] | null> {
  if (isPanelWindow) {
    // The desk window waits for the draw and its checks (desktop/transport.ts); a reply lost past that closes the reveal.
    return requestDesktop<Drop[] | null>("resonate", count, banner).catch((e: unknown) => {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    });
  }
  const session = current;
  const gen = generation;
  // The save's draws so far: a draw whose answer was lost shows as these having gone up.
  const before = status.value?.resonance?.total;
  let r: ResonanceResult;
  let recovered = false;
  try {
    r = await serial(session, () => session.api.resonate(count, banner));
  } catch (e) {
    if (session !== current || gen !== generation) return null;
    // A refusal (4xx) is final. A lost answer (network, timeout, a proxy's 5xx) may hide a draw the server made.
    const lost = !(e instanceof ApiError) || e.status >= 500;
    const found = lost && before !== undefined ? await findDraw(session, gen, before, count, banner) : null;
    if (session !== current || gen !== generation) return null;
    if (!found?.status) {
      fail(e);
      return null;
    }
    status.value = found.status;
    online.value = true;
    if (!found.drops) {
      error.value = "共鸣没有完成，请重试";
      return null;
    }
    // Drawn, but the drops could not be read: the history has them.
    error.value = found.drops.length ? "" : "共鸣已完成，结果在共鸣记录里";
    r = { ...found.status, drops: found.drops };
    recovered = true;
  }
  if (session !== current || gen !== generation) return null;
  status.value = r;
  for (const d of r.drops) {
    // A holo draw is two items: `new` is the holo version's, `cardNew` the card's.
    if (d.holo && d.new) freshItems.add(`holo:${d.item.slice(5)}`);
    if (d.holo ? d.cardNew : d.new) freshItems.add(d.item);
  }
  await reloadCollection();
  // The history keeps no counts: a found draw shows what the save holds now.
  if (recovered) for (const d of r.drops) d.count = collection.owned[d.item] ?? 1;
  return r.drops;
}

/** Waits before each read that looks for a draw whose answer was lost: the server may still be drawing. */
const DRAW_CHECKS_MS = [0, 3000, 6000];

/**
 * Looks for the draw of [count] made from [before] draws in all. `status` null: the server could not be reached;
 * `drops` null: the draw did not happen; an empty list: it did, and its drops could not be read.
 */
async function findDraw(session: Session, gen: number, before: number, count: number, banner?: string):
  Promise<{ status: PlayerStatus | null; drops: Drop[] | null }> {
  let seen: PlayerStatus | null = null;
  for (const wait of DRAW_CHECKS_MS) {
    if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
    if (session !== current || gen !== generation) break;
    try {
      seen = await serial(session, () => session.api.me());
    } catch {
      continue;
    }
    // A draw is all or nothing (one transaction on the server), so the total moves by its whole count.
    if ((seen.resonance?.total ?? before) - before >= count) {
      const drops = await serial(session, () => lastDraws(session.api, count, banner)).catch(() => []);
      return { status: seen, drops };
    }
  }
  return { status: seen, drops: null };
}

/** The last [count] drops drawn from [banner] (the standing pool without one), in the order drawn. */
async function lastDraws(api: Api, count: number, banner?: string): Promise<Drop[]> {
  const rows: HistoryDrop[] = [];
  let next: number | undefined;
  for (let page = 0; page < 3 && rows.length < count; page++) {
    const got = await api.history(next);
    rows.push(...(got.drops ?? []).filter((d) => d.source === "draw" && (d.pool ?? "") === (banner ?? "")));
    if (!got.next) break;
    next = got.next;
  }
  const featured = new Set(banner ? economy.value?.resonance.banners?.find((b) => b.id === banner)?.items : []);
  return rows.slice(0, count).reverse().map((row) => {
    // The history keeps a holo draw as its holo version, and no shards for repeats.
    const holo = row.item.startsWith("holo:");
    const item = holo ? `card:${row.item.slice(5)}` : row.item;
    const card = item.startsWith("card:") ? getCard(item.slice(5)) : undefined;
    return {
      item, rarity: row.rarity as Rarity, new: row.new, count: 1, shards: 0,
      ...(card ? { tier: card.tier } : {}),
      ...(holo ? { holo: true, cardNew: false } : {}),
      ...(featured.has(item) ? { featured: true } : {}),
    };
  });
}

export type HistoryReply = { ok: true; page: DropHistory } | { ok: false; message: string };
/** A page of the save's own drops ([before]: the `next` of the page before), or the line saying why it did not come. */
export async function loadHistory(before?: number): Promise<HistoryReply> {
  const lost: HistoryReply = { ok: false, message: "无法连接服务器" };
  if (isPanelWindow) return requestDesktop<HistoryReply>("loadHistory", before).catch(() => lost);
  const r = await attempt((api) => api.history(before));
  if (!r) return lost;
  if (r.ok) return { ok: true, page: { drops: r.value.drops ?? [], next: r.value.next ?? null } };
  const e = r.error;
  // A server from before the history has no such path.
  if (e instanceof ApiError && e.status === 404) return { ok: false, message: "这个服务器不支持共鸣记录" };
  return e instanceof ApiError && e.status < 500 ? { ok: false, message: e.message } : lost;
}

export async function craftItem(item: string): Promise<boolean> {
  if (isPanelWindow) return requestDesktop("craftItem", item);
  const r = await call((api) => api.craft(item));
  if (!r) return false;
  status.value = r;
  freshItems.add(item);
  await reloadCollection();
  return true;
}

// ---------------------------------------------------------------- daily check-in
/** This month's check-ins, loaded by the check-in page. */
export const checkins = ref<CheckinMonth | null>(null);

export async function loadCheckins(): Promise<void> {
  if (isPanelWindow) return requestDesktop("loadCheckins");
  const month = await call((api) => api.checkinMonth());
  if (month) checkins.value = month;
}

let checkingIn = false;

/** Checks in for today. null when the request failed or today was taken on another device; the month reloads then. */
export async function checkin(): Promise<CheckinResult | null> {
  if (isPanelWindow) return requestDesktop("checkin");
  if (checkingIn) return null;
  checkingIn = true;
  try {
    const r = await call((api) => api.checkin());
    if (!r) {
      await loadCheckins();
      return null;
    }
    status.value = r;
    const { day, index: prize, shards } = r.prize;
    const month = checkins.value;
    if (month && month.today.slice(0, 7) === day.slice(0, 7)) {
      const days = [...month.days.filter((d) => d.day !== day), { day, prize, shards }].sort((x, y) => x.day.localeCompare(y.day));
      checkins.value = { today: day, available: false, days };
    } else {
      await loadCheckins();
    }
    return r;
  } finally {
    checkingIn = false;
  }
}

// ---------------------------------------------------------------- update rewards
/** Update rewards this client's version reaches and the save has not claimed; the server checks the version again. */
export const updateRewards = computed(() =>
  (status.value?.updateRewards ?? []).filter((r) => (compareVersions(APP_VERSION, r.version) ?? -1) >= 0));

let claiming = false;

/** Claims every reward in updateRewards at once; the shards paid, or null when nothing was (the status reloads). */
export async function claimUpdateRewards(): Promise<number | null> {
  if (isPanelWindow) return requestDesktop("claimUpdateRewards");
  if (claiming) return null;
  claiming = true;
  try {
    const r = await call((api) => api.claimUpdateReward());
    if (!r) {
      await reloadStatus();
      return null;
    }
    status.value = r;
    return r.reward.shards;
  } finally {
    claiming = false;
  }
}

// ---------------------------------------------------------------- scratch cards
/** The card bought and not revealed yet, loaded by the scratch page. Its prize is paid when it is revealed. */
export const scratchCard = ref<ScratchCard | null>(null);

export async function loadScratch(): Promise<void> {
  // A server without scratch cards says so in its status; asking it anyway would only raise an error.
  if (!status.value?.scratch) return;
  if (isPanelWindow) return requestDesktop("loadScratch");
  const state = await call((api) => api.scratchState());
  if (state) scratchCard.value = state.card;
}

let buyingScratch = false;

/** Buys a card, or picks up the one still on the table. null when the server refused or could not be reached. */
export async function buyScratch(): Promise<ScratchCard | null> {
  if (isPanelWindow) return requestDesktop("buyScratch");
  if (buyingScratch) return null;
  buyingScratch = true;
  try {
    const r = await call((api) => api.scratchBuy());
    if (!r) return null;
    const { card, ...rest } = r;
    status.value = rest;
    scratchCard.value = card;
    return card;
  } finally {
    buyingScratch = false;
  }
}

/** Collects a card's prize. null when the request failed: the card stays on the table and can be revealed again. */
export async function revealScratch(card: number): Promise<ScratchRevealResult["prize"] | null> {
  if (isPanelWindow) return requestDesktop("revealScratch", card);
  const r = await call((api) => api.scratchReveal(card));
  if (!r) return null;
  const { prize, ...rest } = r;
  status.value = rest;
  if (scratchCard.value?.id === card) scratchCard.value = null;
  if (prize.item) {
    freshItems.add(prize.item);
    await reloadCollection();
  }
  return prize;
}

// ---------------------------------------------------------------- loadout
// Sync the selected character, favorites and name plate. The local values belong to one save (server and player
// id): while that save is selected they are pushed to it; when another save is selected, its stored loadout is
// loaded instead, so switching saves never overwrites one save's loadout with what another save owns.
const LOADOUT_OWNER_KEY = "asoultappo.loadoutOwner.v1";
const saveKey = (base: string, player: string) => `${base}|${player}`;

function loadLoadoutOwner(): string | null {
  try {
    return localStorage.getItem(LOADOUT_OWNER_KEY);
  } catch {
    return null;
  }
}
let loadoutOwner = loadLoadoutOwner();
/** The loadout last pushed to or loaded from the current save, so an unchanged one is not sent again. */
let lastPushed = "";
/** The current save's stored loadout could not be loaded yet. */
let loadoutPending = false;

function setLoadoutOwner(save: string): void {
  loadoutOwner = save;
  try {
    localStorage.setItem(LOADOUT_OWNER_KEY, save);
  } catch {
    /* storage unavailable */
  }
}

/** A save that never chose a character keeps the member of the local one, never a skin it may not own. */
function applyLoadout(l: Loadout): void {
  settings.character = l.character || memberOf(settings.character);
  settings.favorites = Array.isArray(l.favorites) ? l.favorites.slice(0, 8) : [];
  settings.plate = l.plate || "";
  settings.showcase = Array.isArray(l.showcase) ? l.showcase.slice(0, MAX_SHOWCASE) : [];
}

export function localLoadout(): LoadoutPatch {
  return {
    character: settings.character,
    favorites: [...settings.favorites],
    plate: settings.plate || null,
    showcase: [...settings.showcase],
    nick: settings.nick.trim().slice(0, MAX_BOARD_NICK),
    board: settings.onBoard,
  };
}

/** Drop equipped things the player does not own (once the collection is known). */
export function sanitizeLoadout(): void {
  if (!online.value) return;
  const owned = collection.owned;
  if (!ownsCharacter(settings.character, owned)) settings.character = memberOf(settings.character);
  const favs = settings.favorites.filter((k) => ownsEmote(k, owned));
  if (favs.length !== settings.favorites.length) settings.favorites = favs;
  if (settings.plate && !plateUnlocked(settings.plate, owned)) settings.plate = "";
  const shown = settings.showcase.filter((id) => (owned[`card:${id}`] ?? 0) > 0);
  if (shown.length !== settings.showcase.length) settings.showcase = shown;
}

export async function pushLoadout(): Promise<boolean> {
  // status is null between a save switch and its refresh; a different save must load its own loadout first.
  const s = status.value;
  if (!online.value || !s || saveKey(toHttpBase(settings.serverUrl), s.player) !== loadoutOwner) return false;
  const loadout = localLoadout();
  const ok = (await call((api) => api.setLoadout(loadout))) !== null;
  if (ok) lastPushed = JSON.stringify(loadout);
  return ok;
}

let pushTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => [settings.character, settings.favorites.join(","), settings.plate, settings.showcase.join(","), settings.nick, settings.onBoard],
  () => {
    if (isPanelWindow) return;
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => { if (JSON.stringify(localLoadout()) !== lastPushed) void pushLoadout(); }, 400);
  },
);

// ---------------------------------------------------------------- board
// Read-only and never fatal: a server from before the board answers 404, which must not show as an error.
/** The collection board; null when the server has none or does not answer. */
export async function loadBoard(): Promise<Board | null> {
  if (isPanelWindow) return requestDesktop<Board | null>("loadBoard").catch(() => null);
  const session = current;
  return serial(session, () => session.api.board()).catch(() => null);
}

/** The profile of a save on the collection board; null when it is no longer on it or the server does not answer. */
export async function loadBoardProfile(id: string): Promise<MemberProfile | null> {
  if (isPanelWindow) return requestDesktop<MemberProfile | null>("loadBoardProfile", id).catch(() => null);
  const session = current;
  return serial(session, () => session.api.boardProfile(id)).catch(() => null);
}
