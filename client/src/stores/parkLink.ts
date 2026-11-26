// The park's tile matching (docs/design/park-link.md 5 and 6): today's games, the game in play and its result.
// The board is played locally first: a pair taken off the board is removed and shifted here at once, and its move
// joins a queue that goes to the server one move at a time, in order. A move keeps its game and its number (`seq`)
// on every retry, so a resend after a lost answer gets the stored result back, and it never reaches another game.
// A move the server refuses (bad_seq, bad_move) drops the queue and the server's board replaces the local one; the
// board takes no move until it has. A board left with no pair waits for the server's shuffle in the answer to the
// move that left it so. Requests go through the park's request path (stores/park.ts), so the panel's are relayed to
// the desk window like every other park request.
//
// Every request belongs to an epoch, raised whenever the queue is dropped (another game, a resync, a settle, another
// save or server): an answer from an earlier epoch changes nothing.
//
// A server without the link (no_park: it was turned off) is an answer, not a failure: the board and the pending end
// go, its message shows and nothing is asked again until the page asks (loadLink, startLink).
import { computed, ref, shallowRef, watch, type Ref } from "vue";
import { STANDALONE } from "../edition";
import type { ParkState } from "../net/api";
import { toHttpBase } from "../net/protocol";
import { EMPTY, applyShift, findPair, removePair } from "../panel/park/link";
import { parkTry, type ParkError } from "./park";
import { status } from "./player";
import { settings } from "./settings";

export interface LinkGame {
  id: number;
  /** 1 based. */
  level: number;
  rows: number; cols: number;
  shift: "none" | "down" | "left" | "center";
  /** Kind index -> emote key. */
  kinds: string[];
  /** The board, every accepted move and shuffle applied. */
  board: number[];
  /** Moves accepted. */
  seq: number;
  /** Pairs. */
  cleared: number; total: number;
  hints: number;
  seconds: number;
  /** The top prize stored when the game started; missing from servers before it. */
  max?: number;
  /** Server milliseconds when the game started; missing from servers before it. */
  start?: number;
  /** Server milliseconds. */
  deadline: number;
  /** The server's milliseconds when it answered. */
  now: number;
}
export interface LinkResult {
  id: number; level: number;
  cleared: number; total: number;
  /** Shards. */
  prize: number;
  reason: "clear" | "time" | "quit";
  ms: number;
}
export interface LinkState {
  /** Today's settled games, in the order they started. */
  today: LinkResult[];
  /** Games started today, the one in play included. */
  played: number;
  /** Games a day. */
  levels: number;
  game: LinkGame | null;
  last: LinkResult | null;
}

/** A full answer: the state, and the result when a game has just been settled; the status and park come with it. */
interface LinkAnswer { link: LinkState; result?: LinkResult; settled?: boolean; park?: ParkState }
/** A move's answer: the moves accepted and pairs cleared, or a full answer once the game is settled. */
type MoveAnswer = Partial<LinkAnswer> & { seq?: number; cleared?: number; shuffle?: number[] };
/** `t`: milliseconds from the game's start to the pair, by the server's clock; fixed when the pair is taken. */
interface Move { game: number; seq: number; a: number; b: number; t: number }

/** Waits between retries of a request that got no answer. */
const BACKOFF_MS = [400, 800, 1600, 3200, 5000];
/** The end is asked for this long after the local clock runs out. */
const FINISH_AFTER_MS = 200;
const HINTS_KEY = "asoultappo.parkLink.hints.v2";
const SEEN_KEY = "asoultappo.parkLink.seen.v2";
/** Games remembered for hints used and results seen. */
const KEEP = 40;

/** The server's latest state of today's games; null before the first load. */
export const linkState = shallowRef<LinkState | null>(null);
/** The game on the board: the server's, with the local moves applied. Kept after it is settled, under the result. */
export const linkGame = shallowRef<LinkGame | null>(null);
/** A tile's own id at each cell (EMPTY where there is none), moved with the tiles so a view can follow them. */
export const linkTiles = shallowRef<number[]>([]);
/** The result on show: the game just settled here, or an earlier one not seen before. Stays until closed. */
export const linkResult = shallowRef<LinkResult | null>(null);
/** The board has no pair left and waits for the server's shuffle. */
export const linkShuffling = ref(false);
/** The game is being ended: the queue drains, then the server settles it. */
export const linkFinishing = ref(false);
/** The server's board is being fetched to replace the local one; the board takes no move meanwhile. */
export const linkSyncing = ref(false);
/** A start is on its way. */
export const linkStarting = ref(false);
/** Why the latest start or load failed; "" after one that worked. */
export const linkError = ref("");
/** Server time minus local time, in milliseconds. */
export const linkOffset = ref(0);

/** The save the state belongs to: server and player. */
const identity = computed(() => `${toHttpBase(settings.serverUrl)}|${status.value?.player ?? ""}`);
const gameKey = (id: number) => `${identity.value}|${id}`;
/** Hints used, by save and game. */
const hintsUsed = ref<Record<string, number>>(readJson<Record<string, number>>(HINTS_KEY) ?? {});
/** Results seen, by save and game. */
const seen = ref<string[]>(readJson<string[]>(SEEN_KEY) ?? []);

/** A game is on the board and not settled. */
export const linkPlaying = computed(() => !!linkGame.value && !linkResult.value);
/** Hints left on the game in play. */
export const linkHintsLeft = computed(() => {
  const g = linkGame.value;
  return g ? Math.max(0, g.hints - (hintsUsed.value[gameKey(g.id)] ?? 0)) : 0;
});
/** The result to show: the one on show, else the latest one if this save has not seen it. */
export const linkShownResult = computed<LinkResult | null>(() => {
  if (linkResult.value) return linkResult.value;
  const s = linkState.value;
  const last = s?.last;
  if (!s || s.game || linkGame.value || !last || seen.value.includes(gameKey(last.id))) return null;
  return last;
});

/** The server's milliseconds now, by the latest answer that told its time. */
export const serverNow = () => Date.now() + linkOffset.value;

/** How often a page's clock ticks while a game has time left. */
const CLOCK_MS = 200;

/**
 * The server's time for a page that shows the game: it ticks while a game in play has time left and [shown] holds,
 * stands still otherwise and is set to the server's time again whenever that changes. The store's own timer ends
 * the game when its time runs out, shown or not. Call in a component's setup (or an effect scope); stop() ends it.
 */
export function linkClock(shown: () => boolean): { now: Ref<number>; stop: () => void } {
  const now = ref(serverNow());
  let tick: ReturnType<typeof setInterval> | undefined;
  const halt = () => {
    clearInterval(tick);
    tick = undefined;
  };
  const unwatch = watch(() => [linkPlaying.value, linkGame.value?.deadline, shown()] as const, ([on, deadline, visible]) => {
    halt();
    now.value = serverNow();
    if (!on || !visible || !deadline || deadline <= now.value) return;
    tick = setInterval(() => {
      now.value = serverNow();
      if (now.value >= deadline) halt();
    }, CLOCK_MS);
  }, { immediate: true });
  return {
    now,
    stop: () => {
      unwatch();
      halt();
    },
  };
}

let queue: Move[] = [];
/** Moves accepted by the server in the game on the board. */
let accepted = 0;
/** The move request on its way, if any. Only its own answer clears it. */
let inFlight: object | null = null;
let attempts = 0;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let epoch = 0;
/** Raised when the save or server changes: an answer from before then changes nothing at all. */
let session = 0;
/** The game the player asked to end; the end is pursued through resyncs while that game is in play. */
let finishFor: number | null = null;
/** The store has been asked for something: it follows the save from then on. */
let used = false;
let nextTile = 1;
/**
 * The clock that times pairs: the server's time when the game first came onto the board, against the local
 * monotonic clock. Later snapshots of the game never move it (a stale one would set linkOffset back), so the times
 * sent only grow. `last` is the latest time sent for the game.
 */
let anchor: { id: number; server: number; local: number; last: number } | null = null;
let waiters: (() => void)[] = [];
/** Games known settled, latest last: an answer from before that still has one in play is out of date. */
let settledIds: number[] = [];
/** The load on its way and the epoch it was asked in: loads asked meanwhile in that epoch share its answer. */
let loading: { epoch: number; done: Promise<Loaded> } | null = null;

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}
function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: kept for this window only */
  }
}

const retryable = (e: ParkError) => (e.status === 0 && e.code !== "stale") || e.status >= 500;
/** The server has no link, or no longer: an end to syncing, not a failure to try again. */
const linkOff = (e: ParkError) => e.code === "no_park";
const messageOf = (e: ParkError) => (e.status === 0 ? "无法连接服务器" : e.message);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const backoff = (n: number) => BACKOFF_MS[Math.min(n, BACKOFF_MS.length - 1)]!;

function clearRetry(): void {
  clearTimeout(retryTimer);
  retryTimer = undefined;
}
/** Wakes whoever waits for the queue to settle (see idle). */
function wake(): void {
  const list = waiters;
  waiters = [];
  list.forEach((w) => w());
}
/** Nothing is queued, on its way or being fetched again. */
const idle = () => !queue.length && !inFlight && !linkSyncing.value;
async function whenIdle(): Promise<void> {
  while (!idle()) await new Promise<void>((resolve) => waiters.push(resolve));
}
/** Drops the queue; late answers to it are ignored. */
function dropQueue(): void {
  epoch++;
  linkSyncing.value = false;
  queue = [];
  inFlight = null;
  attempts = 0;
  clearRetry();
  linkShuffling.value = false;
  wake();
}

/** The server's clock, from an answer just received: the local deadline then errs late, never early. */
function clock(now: number | undefined): void {
  if (typeof now === "number") linkOffset.value = now - Date.now();
}

/** Fresh tile ids for [board]; the ones of the board shown when it is the same board. */
function tilesFor(board: number[], keep: boolean): number[] {
  const g = linkGame.value;
  if (keep && g && linkTiles.value.length === board.length && g.board.every((v, i) => v === board[i])) return linkTiles.value;
  return board.map((v) => (v === EMPTY ? EMPTY : nextTile++));
}

/** Puts the server's game on the board, dropping the queue. */
function adopt(game: LinkGame): void {
  const same = linkGame.value?.id === game.id;
  if (anchor?.id !== game.id) anchor = { id: game.id, server: game.now, local: performance.now(), last: 0 };
  dropQueue();
  linkTiles.value = tilesFor(game.board, same);
  linkGame.value = game;
  accepted = game.seq;
  if (!same) {
    linkResult.value = null;
    if (finishFor !== null && finishFor !== game.id) stopFinishing();
  }
}

function noteSettled(id: number): void {
  if (!settledIds.includes(id)) settledIds = [...settledIds.slice(-(KEEP - 1)), id];
}

/**
 * Takes the server's state. Its game replaces the one on the board when it is another game, or the same game with
 * everything queued here accepted (or more). A snapshot older than the moves accepted here keeps the local board,
 * and so does one in between: the queue's resends get the server's stored answers.
 */
function take(state: LinkState): void {
  // A game in play there was settled since: the snapshot is out of date.
  if (state.game && settledIds.includes(state.game.id)) return;
  linkState.value = state;
  const game = state.game;
  const local = linkGame.value;
  if (game) {
    clock(game.now);
    // A result on show stays until closed; closing it takes the game in play (dismissResult).
    if (linkResult.value && local?.id !== game.id) return;
    if (!local || local.id !== game.id || game.seq >= accepted + queue.length) adopt(game);
    else linkGame.value = { ...local, deadline: game.deadline, now: game.now, max: game.max ?? local.max };
    return;
  }
  // No game in play: the one on the board was settled elsewhere (its time ran out, or another window ended it).
  if (local && !linkResult.value) {
    if (state.last?.id === local.id) showSettled(state.last);
    else clearBoard();
  }
}

function clearBoard(): void {
  dropQueue();
  linkGame.value = null;
  linkTiles.value = [];
}

/** A settled game's result. A board that does not match it (moves the server never took) leaves with it. */
function showSettled(result: LinkResult): void {
  noteSettled(result.id);
  dropQueue();
  const local = linkGame.value;
  if (local && (local.id !== result.id || local.cleared !== result.cleared)) {
    linkGame.value = null;
    linkTiles.value = [];
  }
  linkResult.value = result;
  if (finishFor === result.id) stopFinishing();
}

/** A full answer that settles the game. */
function settle(d: MoveAnswer): void {
  if (d.link) linkState.value = d.link;
  clock(d.link?.game?.now);
  const result = d.result ?? d.link?.last ?? null;
  if (result) showSettled(result);
  else clearBoard();
}

/** The server has no link: the board, its queue and the end asked for go, and the server's message shows. */
function closeLink(e: ParkError): void {
  stopFinishing();
  clearBoard();
  linkState.value = null;
  linkError.value = messageOf(e);
}

interface Loaded { ok: boolean; park: ParkState | null }
const parkOf = (d: LinkAnswer | undefined) => (d?.park && typeof d.park === "object" ? d.park : null);

function load(): Promise<Loaded> {
  used = true;
  if (loading?.epoch === epoch) return loading.done;
  const mine = epoch;
  const done = (async (): Promise<Loaded> => {
    const r = await parkTry<LinkAnswer>("GET", "/api/park/link");
    if (!r.ok) {
      if (mine === epoch) {
        if (linkOff(r.error)) closeLink(r.error);
        else if (r.error.code !== "stale") linkError.value = messageOf(r.error);
      }
      return { ok: false, park: null };
    }
    if (mine === epoch) {
      linkError.value = "";
      if (r.data?.link) take(r.data.link);
    }
    return { ok: true, park: parkOf(r.data) };
  })();
  const entry = { epoch: mine, done };
  loading = entry;
  void done.finally(() => {
    if (loading === entry) loading = null;
  });
  return done;
}

/** Loads today's games. false when the request failed (linkError says why). */
export async function loadLink(): Promise<boolean> {
  return (await load()).ok;
}

/**
 * Loads today's games for the park page, which then needs no read of its own: the park state that came with them,
 * null when the request failed. A load asked meanwhile (the stall coming into sight) shares the request.
 */
export async function refreshLink(): Promise<ParkState | null> {
  return (await load()).park;
}

/**
 * The server's board replaces the local one. The board takes no move until it has; while there is no answer the load
 * is tried again, until it gets one or the queue's epoch moves on.
 */
async function resync(): Promise<void> {
  dropQueue();
  linkSyncing.value = true;
  const mine = epoch;
  for (let tries = 0; mine === epoch; tries++) {
    const r = await parkTry<LinkAnswer>("GET", "/api/park/link");
    if (mine !== epoch) return;
    if (r.ok && r.data?.link) {
      linkSyncing.value = false;
      const game = r.data.link.game;
      linkState.value = r.data.link;
      // The server's board as it is, whatever the local count says.
      if (game && linkGame.value?.id === game.id && !linkResult.value) {
        clock(game.now);
        adopt(game);
      } else take(r.data.link);
      wake();
      return;
    }
    if (!r.ok && r.error.code === "stale") return;
    if (!r.ok && linkOff(r.error)) {
      closeLink(r.error);
      return;
    }
    await sleep(backoff(tries));
  }
}

/** Starts today's next game (or gets the one in play). false when refused (linkError says why). */
export async function startLink(): Promise<boolean> {
  if (linkStarting.value) return false;
  used = true;
  linkStarting.value = true;
  linkError.value = "";
  const mine = session;
  const r = await parkTry<LinkAnswer>("POST", "/api/park/link/start", {});
  // Another save meanwhile: this answer is not for it.
  if (mine !== session) return false;
  linkStarting.value = false;
  if (!r.ok) {
    if (r.error.code === "stale") return false;
    if (linkOff(r.error)) {
      closeLink(r.error);
      return false;
    }
    const message = messageOf(r.error);
    // No answer: the game may have started and been paid for. A load finds it.
    if (retryable(r.error)) await loadLink();
    if (!linkPlaying.value) linkError.value = message;
    return linkPlaying.value;
  }
  const state = r.data.link;
  // Answered after the game it started was settled here (a load found it first): nothing to take.
  if (state.game && settledIds.includes(state.game.id)) return linkPlaying.value;
  if (linkResult.value) markSeen(linkResult.value.id);
  if (state.game && linkGame.value?.id !== state.game.id) linkResult.value = null;
  // The same game already on the board (found by a load meanwhile) merges like any snapshot and keeps the queue.
  take(state);
  return !!state.game;
}

async function pump(): Promise<void> {
  if (inFlight || retryTimer) return;
  const game = linkGame.value;
  const move = queue[0];
  if (!move || !game || linkResult.value) {
    wake();
    return;
  }
  // A move only ever goes to its own game.
  if (move.game !== game.id) {
    dropQueue();
    return;
  }
  const flight = {};
  inFlight = flight;
  const mine = epoch;
  const r = await parkTry<MoveAnswer>("POST", "/api/park/link/move", { game: move.game, seq: move.seq, a: move.a, b: move.b, t: move.t });
  if (inFlight === flight) inFlight = null;
  if (mine !== epoch || queue[0] !== move) return;
  if (!r.ok) {
    if (retryable(r.error)) {
      retryTimer = setTimeout(() => {
        retryTimer = undefined;
        void pump();
      }, backoff(attempts++));
      return;
    }
    if (r.error.code === "stale") {
      resetLink();
      return;
    }
    if (linkOff(r.error)) {
      closeLink(r.error);
      return;
    }
    await resync();
    return;
  }
  attempts = 0;
  const d = r.data ?? {};
  if (d.settled || d.result || d.link) {
    settle(d);
    return;
  }
  queue.shift();
  accepted = typeof d.seq === "number" ? Math.max(accepted, d.seq) : accepted + 1;
  const g = linkGame.value;
  if (d.shuffle) {
    // Only a board with no pair is shuffled, and no move can follow one.
    if (queue.length || !g || d.shuffle.length !== g.board.length) {
      await resync();
      return;
    }
    linkGame.value = { ...g, board: d.shuffle };
    linkShuffling.value = false;
  } else if (linkShuffling.value && !queue.length) {
    // Stuck here but not on the server: the boards differ.
    await resync();
    return;
  }
  void pump();
}

/** Milliseconds from [g]'s start to now on the pair clock, never less than the last pair's. */
function pairTime(g: LinkGame): number {
  if (anchor?.id !== g.id) anchor = { id: g.id, server: serverNow(), local: performance.now(), last: 0 };
  const start = g.start ?? g.deadline - g.seconds * 1000;
  const t = Math.max(anchor.last, 0, Math.round(anchor.server + (performance.now() - anchor.local) - start));
  anchor.last = t;
  return t;
}

/** Takes the pair [a], [b] off the board and queues its move. false when the board takes no move now. */
export function playPair(a: number, b: number): boolean {
  const g = linkGame.value;
  if (!g || linkResult.value || linkShuffling.value || linkFinishing.value || linkSyncing.value) return false;
  const board = removePair(g.board, g.rows, g.cols, g.shift, a, b);
  const tiles = [...linkTiles.value];
  tiles[a] = EMPTY;
  tiles[b] = EMPTY;
  linkTiles.value = applyShift(tiles, g.rows, g.cols, g.shift);
  linkGame.value = { ...g, board, cleared: g.cleared + 1 };
  queue.push({ game: g.id, seq: accepted + queue.length, a, b, t: pairTime(g) });
  if (board.some((v) => v !== EMPTY) && !findPair(board, g.rows, g.cols)) linkShuffling.value = true;
  void pump();
  return true;
}

function stopFinishing(): void {
  finishFor = null;
  linkFinishing.value = false;
}

/**
 * Ends the game in play: the queued moves go first, then the server settles it (at the deadline as run out, before
 * it as ended). The end holds through a resync while the game stays in play. false when there was nothing to end or
 * the game was settled another way.
 */
export async function finishLink(): Promise<boolean> {
  const g = linkGame.value;
  if (!g || linkResult.value || finishFor === g.id) return false;
  used = true;
  const id = g.id;
  finishFor = id;
  linkFinishing.value = true;
  const live = () => finishFor === id && !linkResult.value && linkGame.value?.id === id;
  for (let tries = 0; live();) {
    await whenIdle();
    if (!live()) break;
    if (!idle()) continue;
    const mine = epoch;
    const r = await parkTry<LinkAnswer>("POST", "/api/park/link/finish", { game: id });
    if (finishFor !== id) break;
    if (r.ok) {
      if (mine === epoch || linkGame.value?.id === id) settle(r.data);
      break;
    }
    if (r.error.code === "stale") break;
    if (linkOff(r.error)) {
      closeLink(r.error);
      break;
    }
    if (!retryable(r.error)) await resync();
    await sleep(backoff(tries++));
  }
  if (finishFor === id) stopFinishing();
  // Read again: the narrowing above does not hold across the awaits.
  return (linkResult.value as LinkResult | null)?.id === id;
}

/** A pair to point out, counting a hint; null when there are none left or no pair is on the board. */
export function takeHint(): [number, number] | null {
  const g = linkGame.value;
  if (!g || linkResult.value || linkHintsLeft.value <= 0) return null;
  const pair = findPair(g.board, g.rows, g.cols);
  if (!pair) return null;
  const key = gameKey(g.id);
  const { [key]: n = 0, ...rest } = hintsUsed.value;
  hintsUsed.value = { ...Object.fromEntries(Object.entries(rest).slice(-(KEEP - 1))), [key]: n + 1 };
  writeJson(HINTS_KEY, hintsUsed.value);
  return [pair[0], pair[1]];
}

function markSeen(id: number): void {
  const key = gameKey(id);
  if (seen.value.includes(key)) return;
  seen.value = [...seen.value.slice(-(KEEP - 1)), key];
  writeJson(SEEN_KEY, seen.value);
}

/** Puts the latest result on show, as seen; it stays until closed. Call when it first becomes visible. */
export function showResult(result: LinkResult): void {
  if (!linkResult.value && !linkGame.value) linkResult.value = result;
  markSeen(result.id);
}

/** Closes the result on show; a game in play elsewhere (in the settling answer or a load) comes onto the board. */
export function dismissResult(): void {
  const shown = linkShownResult.value;
  if (shown) markSeen(shown.id);
  linkResult.value = null;
  linkGame.value = null;
  linkTiles.value = [];
  const next = linkState.value?.game;
  if (next) adopt(next);
}

/** Another save or server: nothing of the last one stays. */
export function resetLink(): void {
  session++;
  anchor = null;
  dropQueue();
  stopFinishing();
  linkStarting.value = false;
  linkState.value = null;
  linkGame.value = null;
  linkTiles.value = [];
  linkResult.value = null;
  linkError.value = "";
  accepted = 0;
  settledIds = [];
  loading = null;
}

// ---------------------------------------------------------------- the store follows the save
// Another server or player (including one passing through no player at all) starts afresh, whoever is showing the
// page; once a player is there again its games load at once.
watch(identity, () => {
  resetLink();
  if (used && status.value?.player && !STANDALONE) void loadLink();
});

// The game ends by itself once its time has run out, whether the page is shown or not.
let autoTimer: ReturnType<typeof setTimeout> | undefined;
watch(() => [linkGame.value?.id, linkGame.value?.deadline, linkPlaying.value] as const, ([id, deadline, playing]) => {
  clearTimeout(autoTimer);
  autoTimer = undefined;
  if (!id || !deadline || !playing) return;
  autoTimer = setTimeout(() => {
    autoTimer = undefined;
    if (linkPlaying.value && linkGame.value?.id === id) void finishLink();
  }, Math.max(0, deadline - serverNow() + FINISH_AFTER_MS));
});
