import { computed, reactive, ref, watch } from "vue";
import {
  Api, ActivityReporter, ApiError, newToken,
  type Collection, type Drop, type LoadoutPatch, type PlayerStatus, type Preset,
} from "../net/api";
import { toHttpBase } from "../net/protocol";
import { manifest } from "../manifest";
import { ownsAccessory, ownsEmote, ownsTheme } from "../items";
import { settings } from "./settings";

const TOKEN_KEY = "asoultappo.token.v1";
export const PRESET_SLOTS = 5;

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

export const token = loadToken();
export const status = ref<PlayerStatus | null>(null);
export const collection = reactive<Collection>({ owned: {}, recent: [] });
export const online = ref(false);
export const error = ref("");
export const boxes = computed(() => status.value?.boxes ?? 0);
export const shards = computed(() => status.value?.shards ?? 0);
export const unlocked = computed(() => new Set(status.value?.unlocked ?? []));
export const presets = ref<(Preset | null)[]>(Array(PRESET_SLOTS).fill(null));
/** Items obtained in this session that the player has not looked at yet. */
export const freshItems = reactive(new Set<string>());

interface Session { api: Api; reporter: ActivityReporter }
const sessions = new Map<string, Session>();
let generation = 0;
let timer: ReturnType<typeof setInterval> | undefined;

function sessionFor(base: string): Session {
  const found = sessions.get(base);
  if (found) return found;
  const api = new Api(() => base, () => token);
  const session: Session = { api, reporter: new ActivityReporter(async (batch) => {
    const gen = generation;
    const result = await api.activity(batch);
    if (current === session && gen === generation) {
      status.value = result;
      online.value = true;
      error.value = "";
    }
  }) };
  sessions.set(base, session);
  return session;
}

let current = sessionFor(toHttpBase(settings.serverUrl));

function fail(e: unknown): void {
  // A rejected request (4xx) means the server is reachable; only network / 5xx errors are "offline".
  if (!(e instanceof ApiError) || e.status >= 500) online.value = false;
  error.value = e instanceof ApiError ? e.message : "无法连接服务器";
}

/** Run a request on the current session; results of older server selections are dropped (null). */
async function call<T>(fn: (api: Api) => Promise<T>): Promise<T | null> {
  const session = current;
  const gen = generation;
  try {
    const r = await fn(session.api);
    return session === current && gen === generation ? r : null;
  } catch (e) {
    if (session === current && gen === generation) fail(e);
    return null;
  }
}

export async function refresh(): Promise<void> {
  const session = current;
  const gen = generation;
  try {
    const [s, c] = await Promise.all([session.api.me(), session.api.collection()]);
    if (session !== current || gen !== generation) return;
    status.value = s;
    collection.owned = c.owned;
    collection.recent = c.recent;
    online.value = true;
    error.value = "";
  } catch (e) {
    if (session === current && gen === generation) fail(e);
    return;
  }
  sanitizeLoadout();
  void pushLoadout();
  void loadPresets();
}

async function flush(session: Session): Promise<boolean> {
  const gen = generation;
  const ok = await session.reporter.flush();
  if (!ok && session === current && gen === generation) online.value = false;
  return ok;
}

watch(() => settings.serverUrl, (url) => {
  const previous = current;
  generation++;
  current = sessionFor(toHttpBase(url));
  status.value = null;
  collection.owned = {};
  collection.recent = [];
  presets.value = Array(PRESET_SLOTS).fill(null);
  freshItems.clear();
  online.value = false;
  error.value = "";
  // Each reporter keeps its original server and batch identity, including retries.
  void flush(previous);
  if (timer) void refresh();
}, { flush: "sync" });

export function countInput(): void {
  current.reporter.add(1);
}

export function startReporting(everyMs = 20000): void {
  if (timer) return;
  void refresh(); // establishes the server's counting baseline before the first batch
  timer = setInterval(() => {
    for (const session of sessions.values()) {
      if (session.reporter.size > 0) void flush(session);
    }
  }, everyMs);
}

export function stopReporting(): void {
  if (timer) clearInterval(timer);
  timer = undefined;
  for (const session of sessions.values()) void flush(session);
}

async function reloadCollection(): Promise<void> {
  const c = await call((api) => api.collection());
  if (c) {
    collection.owned = c.owned;
    collection.recent = c.recent;
  }
}

/** Open up to `count` boxes. Pending taps are reported first so new boxes count. */
export async function openBoxes(count = 1): Promise<Drop[] | null> {
  const session = current;
  const gen = generation;
  if (!await flush(session) || session !== current || gen !== generation) return null;
  const r = await call((api) => api.openBoxes(count));
  if (!r) return null;
  status.value = r;
  for (const d of r.drops) if (d.new) freshItems.add(d.item);
  await reloadCollection();
  return r.drops;
}

export async function craftItem(item: string): Promise<boolean> {
  const r = await call((api) => api.craft(item));
  if (!r) return false;
  status.value = r;
  freshItems.add(item);
  await reloadCollection();
  return true;
}

export async function chooseDecor(patch: { frame?: string; badge?: string }): Promise<boolean> {
  const r = await call((api) => api.setDecor(patch));
  if (!r) return false;
  status.value = r;
  return true;
}

// ---------------------------------------------------------------- loadout
// The local settings are what the pet shows; the server keeps a validated copy so the room
// sees the same accessories and presets can be stored.

export function localLoadout(): LoadoutPatch {
  return {
    character: settings.character,
    head: settings.head,
    desk: settings.desk,
    theme: settings.theme,
    favorites: [...settings.favorites],
  };
}

/** Drop equipped things the player does not own (once the collection is known). */
export function sanitizeLoadout(): void {
  if (!online.value) return;
  const owned = collection.owned;
  if (settings.head && !ownsAccessory(settings.head, owned)) settings.head = "";
  if (settings.desk && !ownsAccessory(settings.desk, owned)) settings.desk = "";
  if (!ownsTheme(settings.theme, owned)) settings.theme = manifest.defaultTheme;
  const favs = settings.favorites.filter((k) => ownsEmote(k, owned));
  if (favs.length !== settings.favorites.length) settings.favorites = favs;
}

export async function pushLoadout(): Promise<boolean> {
  if (!online.value) return false;
  return (await call((api) => api.setLoadout(localLoadout()))) !== null;
}

let pushTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => [settings.character, settings.head, settings.desk, settings.theme, settings.favorites.join(",")],
  () => {
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => void pushLoadout(), 400);
  },
);

export async function loadPresets(): Promise<void> {
  const r = await call((api) => api.presets());
  if (r && Array.isArray(r.presets)) presets.value = r.presets;
}

export async function savePreset(slot: number, name?: string): Promise<boolean> {
  const snapshot: LoadoutPatch = { ...localLoadout(), frame: status.value?.frame ?? "", badge: status.value?.badge ?? "" };
  const r = await call((api) => api.savePreset(slot, snapshot, name));
  if (r) presets.value = r.presets;
  return r !== null;
}

export async function clearPreset(slot: number): Promise<void> {
  const r = await call((api) => api.savePreset(slot, null));
  if (r) presets.value = r.presets;
}

/** Apply a preset; returns the frame/badge patch for the room when decor changed. */
export async function applyPreset(slot: number): Promise<{ frame?: string; badge?: string } | null> {
  const lo = presets.value[slot]?.loadout;
  if (!lo) return null;
  if (lo.character) settings.character = lo.character;
  if (lo.head !== undefined) settings.head = lo.head ?? "";
  if (lo.desk !== undefined) settings.desk = lo.desk ?? "";
  if (lo.theme) settings.theme = lo.theme;
  if (lo.favorites) settings.favorites = [...lo.favorites];
  const decor = { frame: lo.frame ?? "", badge: lo.badge ?? "" };
  if (decor.frame === (status.value?.frame ?? "") && decor.badge === (status.value?.badge ?? "")) return null;
  return await chooseDecor(decor) ? decor : null;
}
