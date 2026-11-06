import { ref } from "vue";
import type { DownloadEvent, Update } from "@tauri-apps/plugin-updater";
import { isTauri } from "../composables/tauri";

const DISMISS_KEY = "asoultappo.update.dismissed";

export const updateOffer = ref<{ version: string; notes: string } | null>(null);
export const updateDialogOpen = ref(false);
export const updateBusy = ref(false);
export const updateFailed = ref(false);
/** Download percent when the server reports a length. Null leaves the label indeterminate. */
export const updatePercent = ref<number | null>(null);

let pending: Update | null = null;
let looked = false;

export async function lookForUpdate(): Promise<void> {
  if (!isTauri || looked) return;
  looked = true;
  try {
    const { check } = await import("@tauri-apps/plugin-updater");
    const found = await check();
    if (!found) return;
    pending = found;
    updateOffer.value = { version: found.version, notes: found.body?.trim() ?? "" };
    let dismissed: string | null = null;
    try {
      dismissed = localStorage.getItem(DISMISS_KEY);
    } catch { /* private mode */ }
    updateDialogOpen.value = dismissed !== found.version;
  } catch {
    pending = null;
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

export async function installUpdate(): Promise<void> {
  const found = pending;
  if (!found || updateBusy.value) return;
  updateBusy.value = true;
  updateFailed.value = false;
  updatePercent.value = null;
  let total = 0;
  let downloaded = 0;
  const onEvent = (event: DownloadEvent) => {
    if (event.event === "Started") {
      downloaded = 0;
      total = event.data.contentLength ?? 0;
      updatePercent.value = total > 0 ? 0 : null;
    } else if (event.event === "Progress") {
      downloaded += event.data.chunkLength;
      updatePercent.value = total > 0 ? Math.min(99, Math.round((downloaded / total) * 100)) : null;
    } else if (total > 0) {
      updatePercent.value = 100;
    }
  };
  try {
    await found.downloadAndInstall(onEvent);
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  } catch {
    updateBusy.value = false;
    updateFailed.value = true;
    updatePercent.value = null;
  }
}
