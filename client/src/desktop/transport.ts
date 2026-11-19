import { emitTo, listen } from "@tauri-apps/api/event";
import { windowLabel, type WindowLabel } from "../composables/tauri";

export type DesktopAction = "sync" | "resonate" | "craftItem" | "checkin" | "claimUpdateRewards" | "loadCheckins" |
  "loadScratch" | "buyScratch" | "revealScratch" | "sendEmote" | "createRoom" | "joinRoom" | "leaveRoom" | "tidyRemotes" |
  "setAccount" | "setRoomPublic" | "setRoomName" | "kickMember" | "loadPublicRooms" | "inviteDuel" | "loadProfile" | "loadBoard" |
  "loadBoardProfile" | "loadEconomy" | "loadHistory" | "park" | "beginPomodoro" | "endPomodoro" | "tryReminder" | "todo" | "todoSync" | "raceSync" | "ddz";

/** `from`: the window that asks and hears the reply: the panel, the todos' window or the race's. */
export interface DesktopRequest { id: string; action: DesktopAction; args: unknown[]; from?: WindowLabel }
interface DesktopReply<T> { result: T; error?: string }

export const DESKTOP_REQUEST_TIMEOUT_MS = 30000;
/**
 * Actions that may run longer. A draw waits for its own longer request and, when that answer is lost, for the reads
 * that find out whether it went through (stores/player.ts): the reply must not time out before those are done.
 */
export const DESKTOP_ACTION_TIMEOUT_MS: Partial<Record<DesktopAction, number>> = { resonate: 120000 };

/** The other windows' actions run in the desk window. Never retry a mutation after a lost reply. */
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
      new Error("桌宠窗口响应超时，请先确认操作结果，勿重复提交")), DESKTOP_ACTION_TIMEOUT_MS[action] ?? DESKTOP_REQUEST_TIMEOUT_MS);
    void (async () => {
      const stop = await listen<DesktopReply<T>>(`desktop:reply:${id}`, ({ payload }) => finish(payload), { target: windowLabel });
      // Registration itself may finish after the timeout or an immediate reply.
      if (settled) { stop(); return; }
      unlisten = stop;
      await emitTo("main", "desktop:request", { id, action, args, from: windowLabel } satisfies DesktopRequest);
    })().catch((error: unknown) => finish(undefined, error instanceof Error ? error : new Error(String(error))));
  });
}
