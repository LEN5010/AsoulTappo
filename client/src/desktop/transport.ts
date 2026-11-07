import { emitTo, listen } from "@tauri-apps/api/event";

export type DesktopAction = "sync" | "resonate" | "craftItem" | "sendEmote" |
  "createRoom" | "joinRoom" | "leaveRoom" | "tidyRemotes" | "setAccount";

export interface DesktopRequest { id: string; action: DesktopAction; args: unknown[] }
interface DesktopReply<T> { result: T; error?: string }

export const DESKTOP_REQUEST_TIMEOUT_MS = 30000;

/** Panel actions run in the desk window. Never retry a mutation after a lost reply. */
export async function requestDesktop<T = void>(action: DesktopAction, ...args: unknown[]): Promise<T> {
  const id = crypto.randomUUID();
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    let unlisten: (() => void) | undefined;
    const finish = (reply?: DesktopReply<T>, error?: unknown) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      unlisten?.();
      if (error) reject(error);
      else if (reply?.error) reject(new Error(reply.error));
      else resolve(reply!.result);
    };
    const timer = setTimeout(() => finish(undefined,
      new Error("桌宠窗口响应超时，请先确认操作结果，勿重复提交")), DESKTOP_REQUEST_TIMEOUT_MS);
    void (async () => {
      const stop = await listen<DesktopReply<T>>(`desktop:reply:${id}`, ({ payload }) => finish(payload), { target: "panel" });
      // Registration itself may finish after the timeout or an immediate reply.
      if (settled) { stop(); return; }
      unlisten = stop;
      await emitTo("main", "desktop:request", { id, action, args } satisfies DesktopRequest);
    })().catch((error: unknown) => finish(undefined, error instanceof Error ? error : new Error(String(error))));
  });
}
