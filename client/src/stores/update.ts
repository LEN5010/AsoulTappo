// Update check. The newest version comes from the room server, which reads the main site's release
// list: many players cannot reach GitHub. The signed package itself still comes from GitHub through
// the Tauri updater; when that fails, the download page on the main site opens instead.
import { ref } from "vue";
import type { Update } from "@tauri-apps/plugin-updater";
import { isTauri, openAboutLink } from "../composables/tauri";
import { Api, type ReleaseInfo } from "../net/api";
import { toHttpBase } from "../net/protocol";
import { isNewer } from "../semver";
import { settings } from "./settings";

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
    return typeof found?.version === "string" ? { version: found.version, notes: found.notes?.trim() ?? "" } : null;
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

/** Looks for a newer version: once by itself when the panel opens, or again from the settings page. */
export async function lookForUpdate(manual = false): Promise<void> {
  if (checkState.value === "checking" || updateBusy.value) return;
  if (!manual) {
    if (looked) return;
    looked = true;
  } else {
    checkState.value = "checking";
  }
  const latest = await askServer();
  if (latest) {
    if (isNewer(latest.version, __APP_VERSION__)) offer(latest, manual);
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

export function openUpdateDialog(): void {
  if (!updateOffer.value) return;
  if (!updateBusy.value) updateFailed.value = false;
  updateDialogOpen.value = true;
}

export function dismissUpdate(): void {
  if (updateBusy.value) return;
  const version = updateOffer.value?.version;
  if (version) {
    try {
      localStorage.setItem(DISMISS_KEY, version);
    } catch { /* private mode */ }
  }
  updateDialogOpen.value = false;
  updateFailed.value = false;
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
 * Installs the offered version from its own GitHub release (`v<version>`) and restarts; opens the
 * download page if that fails. Not `releases/latest`: GitHub never points that at a pre-release.
 */
export async function installUpdate(): Promise<void> {
  const want = updateOffer.value?.version;
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
    // False: that release has no package for this version yet (still uploading), so the download page.
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
