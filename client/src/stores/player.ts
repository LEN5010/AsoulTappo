import { computed, reactive, ref, watch } from "vue";
import { Api, ActivityReporter, ApiError, newToken, type Collection, type OpenResult, type PlayerStatus } from "../net/api";
import { toHttpBase } from "../net/protocol";
import { settings } from "./settings";

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

export const token = loadToken();
export const status = ref<PlayerStatus | null>(null);
export const collection = reactive<Collection>({ owned: {}, recent: [] });
export const online = ref(false);
export const error = ref("");
export const boxes = computed(() => status.value?.boxes ?? 0);
export const lastOpened = ref<OpenResult | null>(null);

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
  online.value = false;
  error.value = e instanceof ApiError ? e.message : "无法连接服务器";
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
  }
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
  lastOpened.value = null;
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

export async function openBox(): Promise<OpenResult | null> {
  const session = current;
  const gen = generation;
  try {
    if (!await flush(session) || session !== current || gen !== generation) return null;
    const r = await session.api.openBox();
    if (session !== current || gen !== generation) return null;
    lastOpened.value = r;
    await refresh();
    return session === current && gen === generation ? r : null;
  } catch (e) {
    if (session === current && gen === generation) fail(e);
    return null;
  }
}

export async function chooseDecor(patch: { frame?: string; badge?: string }): Promise<boolean> {
  const session = current;
  const gen = generation;
  try {
    const r = await session.api.setDecor(patch);
    if (session !== current || gen !== generation) return false;
    status.value = r;
    return true;
  } catch (e) {
    if (session === current && gen === generation) fail(e);
    return false;
  }
}
