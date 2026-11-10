// Account sign-in sends the main-site password and token. Only the official deployment may receive them:
// a self-hosted server could advertise its own account service, or pass on the token it receives.
const TRUSTED_ORIGINS = ["https://len5010.top"];
const DEV_HOSTS = ["localhost", "127.0.0.1"];

/** Whether [url] is on the official origin; dev builds also accept local http servers on any port. */
export function trustedOrigin(url: string | null | undefined, dev: boolean = import.meta.env.DEV): boolean {
  if (!url) return false;
  let u: URL;
  try {
    u = new URL(url.trim());
  } catch {
    return false;
  }
  if (TRUSTED_ORIGINS.includes(u.origin)) return true;
  return dev && u.protocol === "http:" && DEV_HOSTS.includes(u.hostname);
}

/** Account sign-in is offered only when both the room server and its advertised account service are trusted. */
export function accountLoginTrusted(server: string, mainApi: string | null | undefined, dev: boolean = import.meta.env.DEV): boolean {
  return trustedOrigin(server, dev) && trustedOrigin(mainApi, dev);
}
