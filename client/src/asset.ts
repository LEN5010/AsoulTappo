// Asset URL resolution against the applied server (reactive when used in templates).
import { computed } from "vue";
import { resolveAsset } from "./manifest";
import { toHttpBase } from "./net/protocol";
import { settings } from "./stores/settings";

export const serverBase = computed(() => toHttpBase(settings.serverUrl));

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
