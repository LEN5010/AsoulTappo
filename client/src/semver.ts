// Version order for the update check: x.y.z, then a pre-release (`-beta.6`) sorts below its release.

const PATTERN = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/;

function compareIds(a: string, b: string): number {
  const na = /^\d+$/.test(a), nb = /^\d+$/.test(b);
  if (na && nb) return Number(a) - Number(b);
  if (na !== nb) return na ? -1 : 1;
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Negative, zero or positive as `a` is older than, the same as or newer than `b`; null if either is not a version. */
export function compareVersions(a: string, b: string): number | null {
  const x = PATTERN.exec(a.trim()), y = PATTERN.exec(b.trim());
  if (!x || !y) return null;
  for (let i = 1; i <= 3; i++) {
    const d = Number(x[i]) - Number(y[i]);
    if (d) return d;
  }
  const px = x[4]?.split(".") ?? [], py = y[4]?.split(".") ?? [];
  if (!px.length || !py.length) return py.length - px.length;
  for (let i = 0; i < Math.max(px.length, py.length); i++) {
    if (i >= px.length) return -1;
    if (i >= py.length) return 1;
    const d = compareIds(px[i]!, py[i]!);
    if (d) return d;
  }
  return 0;
}

export const isNewer = (candidate: string, current: string) => (compareVersions(candidate, current) ?? 0) > 0;
