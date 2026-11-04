import { emitTo, listen } from "@tauri-apps/api/event";

export type DesktopAction = "sync" | "drawCards" | "openBoxes" | "craftItem" | "sendEmote" |
  "createRoom" | "joinRoom" | "leaveRoom" | "tidyRemotes";

export interface DesktopRequest { id: string; action: DesktopAction; args: unknown[] }
interface DesktopReply<T> { result: T; error?: string }

/** Panel actions run in the desk window, which owns the network and activity counters. */
export async function requestDesktop<T = void>(action: DesktopAction, ...args: unknown[]): Promise<T> {
  const id = crypto.randomUUID();
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const result = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  const unlisten = await listen<DesktopReply<T>>(`desktop:reply:${id}`, ({ payload }) => {
    unlisten();
    if (payload.error) reject(new Error(payload.error));
    else resolve(payload.result);
  }, { target: "panel" });
  try {
    await emitTo("main", "desktop:request", { id, action, args } satisfies DesktopRequest);
  } catch (e) {
    unlisten();
    throw e;
  }
  return result;
}
