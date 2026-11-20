// Update check. The newest version comes from the room server, which reads the main site's release
// list: many players cannot reach GitHub. The signed package itself still comes from GitHub through
// the Tauri updater; when that fails, the dialog offers the download page on the main site.
import { computed, ref, watch } from "vue";
import type { Update } from "@tauri-apps/plugin-updater";
import { isPanelWindow, isTauri, openAboutLink, writeLog } from "../composables/tauri";
import { agreed } from "../legal/consent";
import { Api, type Announcement, type ReleaseInfo } from "../net/api";
import { toHttpBase } from "../net/protocol";
import { isNewer } from "../semver";
import { dayKey } from "./counter";
import { settings } from "./settings";
import { APP_VERSION } from "../version";

const DISMISS_KEY = "asoultappo.update.dismissed";
/** Every installer, mirrored on the main site. Also listed in ABOUT_LINKS (src-tauri/src/lib.rs). */
export const DOWNLOAD_PAGE = "https://len5010.top/dynamics/download?app=tappo";
const GITHUB_TIMEOUT_MS = 15000;

export const updateOffer = ref<ReleaseInfo | null>(null);
export const updateDialogOpen = ref(false);
export const updateBusy = ref(false);
export const updateFailed = ref(false);
/** Download percent when the server reports a length. Null leaves the label indeterminate. */
export const updatePercent = ref<number | null>(null);
/** The check started from the settings page: running, nothing newer, or no answer from anywhere. */
export const checkState = ref<"idle" | "checking" | "latest" | "failed">("idle");

/** This version is below the server's minimum: the dialog stays until the update is installed. */
export const updateForced = ref(false);

// ---- announcements, read with the update check and kept on the notice board, one page each. The board opens by
// itself while one is due: not closed yet, or for a daily one, not closed today.
const SEEN_KEY = "asoultappo.notices.seen";
const SEEN_KEPT = 50;
/** Daily announcements: the China day each was last closed on. */
const DAILY_KEY = "asoultappo.notices.daily";
const DAY_ZONE = "Asia/Shanghai";
function loadSeen(): string[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}
function loadDaily(): Record<string, string> {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(DAILY_KEY) ?? "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    return Object.fromEntries(Object.entries(raw).filter((e): e is [string, string] => typeof e[1] === "string"));
  } catch {
    return {};
  }
}
const announcements = ref<Announcement[]>([]);
const seen = ref<string[]>(loadSeen());
const dailyClosed = ref<Record<string, string>>(loadDaily());
/** The board's pages: every announcement the server lists now, newest first (by date, then by list order). */
export const notices = computed<readonly Announcement[]>(() =>
  announcements.value.map((a, i) => ({ a, i }))
    .sort((x, y) => (y.a.since ?? 0) - (x.a.since ?? 0) || y.i - x.i)
    .map(({ a }) => a));
/**
 * The announcements due on this device, newest first. The day is read whenever the list comes again (every half
 * hour), so a new day brings a daily one back.
 */
export const dueNotices = computed<readonly Announcement[]>(() => {
  const today = dayKey();
  return notices.value.filter((a) => !seen.value.includes(a.id) && !(a.daily && dailyClosed.value[a.id] === today));
});
/** Opened from the top bar. */
const boardAsked = ref(false);
/** The notice board: opened from the top bar, or by itself while an announcement is due; the update dialog first. */
export const noticeBoardShown = computed(() =>
  !updateDialogOpen.value && notices.value.length > 0 && (boardAsked.value || dueNotices.value.length > 0));
export function openNoticeBoard(): void {
  boardAsked.value = true;
}
/** Closing the board closes every announcement due on it: for good, or until tomorrow for a daily one. */
export function closeNoticeBoard(): void {
  boardAsked.value = false;
  for (const notice of [...dueNotices.value]) closeNotice(notice);
}
function closeNotice(notice: Announcement): void {
  if (!notice.daily) {
    readNotice(notice.id);
    return;
  }
  const kept = Object.entries(dailyClosed.value).filter(([id]) => id !== notice.id).slice(-(SEEN_KEPT - 1));
  dailyClosed.value = Object.fromEntries([...kept, [notice.id, dayKey()]]);
  try {
    localStorage.setItem(DAILY_KEY, JSON.stringify(dailyClosed.value));
  } catch { /* private mode */ }
}
// A fresh install starts with the backlog put away: every announcement listed when the first list arrives counts as
// read, the newest one aside. Kept until that list arrives, also over a restart (consent comes before the network).
const QUIET_KEY = "asoultappo.notices.quiet";
let quiet = (() => {
  try { return localStorage.getItem(QUIET_KEY) === "1"; } catch { return false; }
})();
/** Called on the first consent of this device: the announcements listed when the next list arrives are put away. */
export function quietBacklog(): void {
  quiet = true;
  try { localStorage.setItem(QUIET_KEY, "1"); } catch { /* private mode */ }
}
function putBacklogAway(): void {
  quiet = false;
  try { localStorage.removeItem(QUIET_KEY); } catch { /* private mode */ }
  for (const notice of notices.value.slice(1)) closeNotice(notice);
}

/** Whether this device has closed the announcement [id] for good; the launch spotlight keeps its id in the same list. */
export const noticeSeen = (id: string) => seen.value.includes(id);
/** Closes the announcement [id] for good: a daily one stops coming back. */
export function readNotice(id: string): void {
  seen.value = [...seen.value.filter((s) => s !== id), id].slice(-SEEN_KEPT);
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(seen.value));
  } catch { /* private mode */ }
}
/** An announcement's date on the board: 11月15日, with the year when it is not this China year. */
export function noticeDate(since: number, now = Date.now()): string {
  const parts = (t: number) => Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: DAY_ZONE, year: "numeric", month: "numeric", day: "numeric" })
      .formatToParts(new Date(t)).map((p) => [p.type, p.value]));
  const day = parts(since * 1000);
  const year = day.year === parts(now).year ? "" : `${day.year}年`;
  return `${year}${day.month}月${day.day}日`;
}
const isNotice = (a: unknown): a is Announcement => {
  const n = a as Partial<Announcement> | null;
  return typeof n?.id === "string" && typeof n.title === "string" && typeof (n.body ?? "") === "string"
    && (n.daily === undefined || typeof n.daily === "boolean") && (n.since === undefined || typeof n.since === "number");
};

type GithubAnswer = { ok: true; update: Update | null } | { ok: false };
let github: Promise<GithubAnswer> | null = null;
let looked = false;

/** The Tauri updater's answer from GitHub, asked once and shared; asked again after a failure. */
function askGithub(again = false): Promise<GithubAnswer> {
  if (!isTauri) return Promise.resolve({ ok: false });
  if (!github || again) {
    github = import("@tauri-apps/plugin-updater")
      .then(({ check }) => check({ timeout: GITHUB_TIMEOUT_MS }))
      .then((update): GithubAnswer => ({ ok: true, update }), (): GithubAnswer => ({ ok: false }));
  }
  return github;
}

async function askServer(): Promise<ReleaseInfo | null> {
  try {
    const found = await new Api(() => toHttpBase(settings.serverUrl), () => "").latestRelease();
    if (typeof found?.version !== "string") return null;
    return {
      version: found.version, notes: found.notes?.trim() ?? "",
      minVersion: typeof found.minVersion === "string" ? found.minVersion : null,
      announcements: Array.isArray(found.announcements) ? found.announcements.filter(isNotice).map((a) => ({ ...a, body: a.body ?? "" })) : [],
    };
  } catch {
    return null;
  }
}

function offer(found: ReleaseInfo, manual: boolean): void {
  updateOffer.value = found;
  checkState.value = "idle";
  if (!updateBusy.value) updateFailed.value = false;
  let dismissed: string | null = null;
  try {
    dismissed = localStorage.getItem(DISMISS_KEY);
  } catch { /* private mode */ }
  updateDialogOpen.value = manual || dismissed !== found.version;
}

/** The first check of this window has an answer, or has none to come: what the panel opens with is known. */
export const releaseChecked = ref(false);

/** Asks again when the panel comes back up: until the answer is in, what it opens with is not known again. */
export async function recheckRelease(): Promise<void> {
  releaseChecked.value = false;
  try {
    await lookForUpdate(false, true);
  } finally {
    releaseChecked.value = true;
  }
}

/**
 * Looks for a newer version: once by itself when the panel opens, again from the settings page ([manual]),
 * or again on the release watch ([again]). The server's answer also carries its minimum version and announcements.
 */
export async function lookForUpdate(manual = false, again = false): Promise<void> {
  if (checkState.value === "checking" || updateBusy.value) return;
  if (!manual && !agreed.value) return;
  if (!manual) {
    if (looked && !again) return;
    looked = true;
  } else {
    checkState.value = "checking";
  }
  try {
    await check(manual);
  } finally {
    releaseChecked.value = true;
  }
}

async function check(manual: boolean): Promise<void> {
  const latest = await askServer();
  if (latest) {
    announcements.value = latest.announcements ?? [];
    // The board is the panel's (the desk window of the app reads the list too, for the minimum version).
    if (quiet && (isPanelWindow || !isTauri)) putBacklogAway();
    const must = !!latest.minVersion && isNewer(latest.minVersion, APP_VERSION);
    updateForced.value = must;
    if (isNewer(latest.version, APP_VERSION)) offer(latest, manual || must);
    else if (must) offer({ version: latest.minVersion!, notes: "" }, true);
    else if (manual) checkState.value = "latest";
    return;
  }
  // The server could not say: GitHub, if this device reaches it.
  const answer = await askGithub(manual);
  if (!answer.ok) {
    if (manual) checkState.value = "failed";
  } else if (answer.update) {
    offer({ version: answer.update.version, notes: answer.update.body?.trim() ?? "" }, manual);
  } else if (manual) {
    checkState.value = "latest";
  }
}

const WATCH_MS = 30 * 60 * 1000;
/** Asks again now and every half hour, so a minimum version or an announcement set later still arrives. */
export function watchRelease(): () => void {
  let timer: ReturnType<typeof setInterval> | undefined;
  // Nothing is asked before the player agrees to the terms (src/legal); agreeing starts the watch.
  const stop = watch(agreed, (ok) => {
    if (!ok || timer) return;
    void lookForUpdate(false, true);
    timer = setInterval(() => void lookForUpdate(false, true), WATCH_MS);
  }, { immediate: true });
  return () => { stop(); clearInterval(timer); };
}

export function openUpdateDialog(): void {
  if (!updateOffer.value) return;
  if (!updateBusy.value) updateFailed.value = false;
  updateDialogOpen.value = true;
}

export function dismissUpdate(): void {
  if (updateBusy.value || updateForced.value) return;
  const version = updateOffer.value?.version;
  if (version) {
    try {
      localStorage.setItem(DISMISS_KEY, version);
    } catch { /* private mode */ }
  }
  updateDialogOpen.value = false;
  updateFailed.value = false;
}

/** The main site's download page, for players whose connection to GitHub is too slow or blocked. */
export function openDownloadPage(): void {
  openAboutLink(DOWNLOAD_PAGE);
}

function failed(): void {
  updateBusy.value = false;
  updateFailed.value = true;
  updatePercent.value = null;
}

type InstallEvent =
  | { event: "Started"; data: { content_length: number | null } }
  | { event: "Progress"; data: { chunk_length: number } }
  | { event: "Finished" };

/**
 * Installs the offered version from its own GitHub release (`v<version>`) and restarts; on failure the
 * dialog's button turns into a link to the download page. Not `releases/latest`: GitHub never points that at a pre-release.
 */
export async function installUpdate(): Promise<void> {
  const want = updateOffer.value?.version;
  writeLog("update", `install ${want ?? "none"}, busy ${updateBusy.value}, failed ${updateFailed.value}`);
  if (!want || updateBusy.value) return;
  if (updateFailed.value || !isTauri) {
    openAboutLink(DOWNLOAD_PAGE);
    return;
  }
  updateBusy.value = true;
  updatePercent.value = null;
  let total = 0;
  let downloaded = 0;
  try {
    const { invoke, Channel } = await import("@tauri-apps/api/core");
    const onEvent = new Channel<InstallEvent>();
    onEvent.onmessage = (event) => {
      if (event.event === "Started") {
        downloaded = 0;
        total = event.data.content_length ?? 0;
        updatePercent.value = total > 0 ? 0 : null;
      } else if (event.event === "Progress") {
        downloaded += event.data.chunk_length;
        updatePercent.value = total > 0 ? Math.min(99, Math.round((downloaded / total) * 100)) : null;
      } else if (total > 0) {
        updatePercent.value = 100;
      }
    };
    // False: that release has no package for this version yet (still uploading); the dialog offers the download page.
    const installed = await invoke<boolean>("install_version", { version: want.replace(/^v/, "").split("+")[0], onEvent });
    if (!installed) {
      failed();
      return;
    }
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  } catch {
    failed();
  }
}
