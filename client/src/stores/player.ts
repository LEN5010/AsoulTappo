import { computed, reactive, ref } from "vue";
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
    return newToken(); // storage unavailable: progress lives for this session only
  }
}

/** Secret identity of this player on the server (never shown to other players). */
export const token = loadToken();

export const api = new Api(() => toHttpBase(settings.serverUrl), () => token);

export const status = ref<PlayerStatus | null>(null);
export const collection = reactive<Collection>({ owned: {}, recent: [] });
export const online = ref(false);
export const error = ref("");

function fail(e: unknown): void {
  online.value = false;
  error.value = e instanceof ApiError ? e.message : "无法连接服务器";
}

export async function refresh(): Promise<void> {
  try {
    status.value = await api.me();
    const c = await api.collection();
    collection.owned = c.owned;
    collection.recent = c.recent;
    online.value = true;
    error.value = "";
  } catch (e) {
    fail(e);
  }
}

const reporter = new ActivityReporter(async (n) => {
  status.value = await api.activity(n);
  online.value = true;
});

/** Count one input (key press / click) toward box progress. Only the count is ever sent. */
export function countInput(): void {
  reporter.add(1);
}

let timer: ReturnType<typeof setInterval> | undefined;
export function startReporting(everyMs = 20000): void {
  if (timer) return;
  void refresh();
  timer = setInterval(() => {
    if (reporter.size > 0) void reporter.flush().then((ok) => ok || (online.value = false));
  }, everyMs);
}
export function stopReporting(): void {
  if (timer) clearInterval(timer);
  timer = undefined;
}

export const boxes = computed(() => status.value?.boxes ?? 0);
export const lastOpened = ref<OpenResult | null>(null);

export async function openBox(): Promise<OpenResult | null> {
  try {
    await reporter.flush(); // make sure the latest taps are counted first
    const r = await api.openBox();
    lastOpened.value = r;
    await refresh();
    return r;
  } catch (e) {
    fail(e);
    return null;
  }
}

export async function chooseDecor(patch: { frame?: string; badge?: string }): Promise<void> {
  try {
    const r = await api.setDecor(patch);
    if (status.value) Object.assign(status.value, r);
  } catch (e) {
    fail(e);
  }
}
