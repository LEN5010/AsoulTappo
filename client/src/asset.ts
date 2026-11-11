// Asset URL resolution against the applied server (reactive when used in templates).
import { computed } from "vue";
import { resolveAsset } from "./manifest";
import { toHttpBase } from "./net/protocol";
import { settings } from "./stores/settings";
import { agreed } from "./legal/consent";

/** Empty until the player agrees to the terms (src/legal): files from the server wait for that too. */
export const serverBase = computed(() => (agreed.value ? toHttpBase(settings.serverUrl) : ""));

export function assetUrl(ref: string | null | undefined): string {
  return resolveAsset(ref, serverBase.value, import.meta.env.BASE_URL || "/");
}

const blobs = new Map<string, Promise<Blob | null>>();

/**
 * A fresh URL for an animated image, so it plays from its first frame every time
 * (the same URL shares one animation timeline). Falls back to the plain URL.
 */
export async function freshAnimationUrl(url: string): Promise<{ url: string; release(): void }> {
  if (!blobs.has(url)) {
    blobs.set(url, fetch(url).then((r) => (r.ok ? r.blob() : null), () => null));
  }
  const blob = await blobs.get(url)!;
  if (!blob) {
    blobs.delete(url);
    return { url, release() {} };
  }
  const u = URL.createObjectURL(blob);
  return { url: u, release: () => URL.revokeObjectURL(u) };
}

const warmed = new Set<string>();
/**
 * Asks for the first byte of a bundled video ahead of its playback. On macOS the app unpacks the whole
 * video for that (src-tauri/src/media.rs), so the player that follows starts without the wait.
 * Other platforms answer a range with the whole file and are left alone.
 */
export function warmVideo(url: string): void {
  if (!url || location.protocol !== "tauri:" || warmed.has(url)) return;
  warmed.add(url);
  // The app keeps only a few videos; let a later hover warm this one again.
  setTimeout(() => warmed.delete(url), 30_000);
  void fetch(url, { headers: { Range: "bytes=0-0" } }).catch(() => {});
}
