// Main-site (len5010.top) account requests. The desk pet signs in natively with client_id "asoultappo"
// and keeps the returned Bearer token; the room server only receives that token to find the linked save.
import type { MainUser } from "./api";
import type { FetchLike } from "./api";

export interface MainSession { token: string; user: MainUser }

const CLIENT_ID = "asoultappo";

export class MainAccountApi {
  constructor(private base: string, private f: FetchLike = (u, i) => fetch(u, i)) {}

  private async call<T>(path: string, body?: Record<string, unknown>, token?: string): Promise<T> {
    let res: Response;
    try {
      res = await this.f(`${this.base.replace(/\/+$/, "")}/${path}`, {
        method: body ? "POST" : "GET",
        headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error("连不上账号服务，请检查网络");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.error === "string" ? data.error : `账号服务返回 ${res.status}`);
    return data as T;
  }

  private async session(path: string, body: Record<string, unknown>): Promise<MainSession> {
    const data = await this.call<{ access_token: string; user: MainUser }>(path, { client_id: CLIENT_ID, ...body });
    return { token: data.access_token, user: { id: data.user.id, username: data.user.username, email: data.user.email ?? null } };
  }

  /** [account] is a username or a verified email address. */
  login = (account: string, password: string) => this.session("auth/native/login", { username: account, password });
  sendRegistrationCode = (email: string) => this.call("auth/register/code", { client_id: CLIENT_ID, email });
  register = (username: string, email: string, code: string, password: string) =>
    this.session("auth/native/register", { username, email, code, password });
  requestPasswordReset = (account: string) => this.call("auth/password-reset/request", { client_id: CLIENT_ID, account });
  confirmPasswordReset = (account: string, code: string, newPassword: string) =>
    this.call("auth/password-reset/confirm", { account, code, newPassword });
  /** Old accounts bind an address before they can link a save. */
  sendEmailCode = (token: string, email: string) => this.call("account/email", { email }, token);
  verifyEmail = (token: string, code: string) =>
    this.call<{ email: string }>("account/email/verify", { code }, token).then((r) => r.email);
  revoke = (token: string) => this.call("oauth/revoke", {}, token);
}
