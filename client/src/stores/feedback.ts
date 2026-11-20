// Feedback from the settings page (server/app/feedback.py). The desk window sends it and reads the log itself, so the
// log never travels between the windows.
import { isMirrorWindow, logTail } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { ApiError } from "../net/api";
import { attempt } from "./player";

/** What the server takes (server/app/feedback.py). */
export const FEEDBACK_TEXT_MAX = 1000;
export const FEEDBACK_CONTACT_MAX = 100;
const SYSTEM_MAX = 200;

/** What the player wrote, and whether the log goes with it. */
export interface FeedbackDraft { text: string; contact: string; log: boolean }
/** Sent, with how many more the save may send today; or why not. */
export type FeedbackResult = { ok: true; left: number } | { ok: false; message: string };

const FAILED = "发送失败，请检查网络后再试";

export async function sendFeedback(draft: FeedbackDraft): Promise<FeedbackResult> {
  if (isMirrorWindow) {
    try {
      return await requestDesktop<FeedbackResult>("feedback", draft);
    } catch {
      return { ok: false, message: FAILED };
    }
  }
  const log = draft.log ? await logTail().catch(() => "") : "";
  const r = await attempt((api) => api.feedback({
    text: draft.text.trim().slice(0, FEEDBACK_TEXT_MAX),
    contact: draft.contact.trim().slice(0, FEEDBACK_CONTACT_MAX),
    system: navigator.userAgent.slice(0, SYSTEM_MAX),
    log,
  }));
  if (r?.ok) return { ok: true, left: r.value.left };
  // The server's own words for a refusal (the day's limit); anything else is the network or the server.
  const e = r?.error;
  return { ok: false, message: e instanceof ApiError && e.status >= 400 && e.status < 500 && e.code !== "http_error" ? e.message : FAILED };
}
