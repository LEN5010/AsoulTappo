// Which installer this build is. The standalone edition (npm run build:standalone) never connects to a server: every
// item is owned from the start and only the backpack, the album and the settings remain. The constant is fixed at
// build time (vite.config.ts), so either edition's dead branches can be dropped by the minifier.

export const STANDALONE: boolean = __STANDALONE__;

/** Paths only a server answers; in the standalone edition the app's own origin serves none of them. */
const SERVER_PATHS = /^\/(api|rooms|ws|packs|auth|account|oauth)(\/|$|\?)/;

/**
 * Whether [url] stays inside the app: the page's own scheme and host (bundled files, the macOS media protocol on the
 * same scheme), or a blob or data URL made by the page. Compared by scheme and host rather than `origin`, which is
 * "null" for every custom scheme such as tauri://.
 */
export function isLocalUrl(url: string, here: string | undefined = globalThis.location?.href): boolean {
  try {
    const u = new URL(url, here);
    if (u.protocol === "blob:" || u.protocol === "data:") return true;
    if (!here) return false;
    const h = new URL(here);
    return u.protocol === h.protocol && u.host === h.host;
  } catch {
    return false;
  }
}

/** Whether [url] would reach a server: anywhere off the app, or a server path on it (an empty server base). */
export function isServerUrl(url: string, here: string | undefined = globalThis.location?.href): boolean {
  if (!isLocalUrl(url, here)) return true;
  try {
    return SERVER_PATHS.test(new URL(url, here).pathname);
  } catch {
    return true;
  }
}

/** Thrown in the standalone edition by every place that would open a connection. */
export class StandaloneRefused extends Error {
  constructor(url: string) {
    super(`standalone edition: no connection to ${url}`);
  }
}

/** The standalone edition's second line behind "nothing starts": refuses a server request before it is made. */
export function refuseServer(url: string): void {
  if (STANDALONE && isServerUrl(url)) throw new StandaloneRefused(url);
}

/** The standalone edition's guard for bundled files: anything off the app's own origin is refused. */
export function refuseRemote(url: string): void {
  if (STANDALONE && !isLocalUrl(url)) throw new StandaloneRefused(url);
}

const urlOf = (input: RequestInfo | URL) => (typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

/** fetch for server requests: in the standalone edition it rejects without sending anything. */
export function serverFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    refuseServer(urlOf(input));
  } catch (e) {
    return Promise.reject(e);
  }
  return fetch(input, init);
}

/** fetch for bundled files: in the standalone edition it rejects anything off the app's own origin. */
export function localFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    refuseRemote(urlOf(input));
  } catch (e) {
    return Promise.reject(e);
  }
  return fetch(input, init);
}
