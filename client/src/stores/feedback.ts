// Feedback from the settings page (server/app/feedback.py). The desk window sends it and reads the log itself, so the
// log never travels between the windows. The window with the dialog sends one draft at a time (submitFeedback): a
// dialog opened again while a send is out follows that send, and each draft carries a request id until a send of it
// goes through, so a resend after a lost answer is the same feedback to the server.
import { shallowRef } from "vue";
import { isMirrorWindow, logTail } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { ApiError, type FeedbackBody } from "../net/api";
import { attempt } from "./player";
import { settings } from "./settings";

/** What the server takes (server/app/feedback.py). */
export const FEEDBACK_TEXT_MAX = 1000;
export const FEEDBACK_CONTACT_MAX = 100;
const SYSTEM_MAX = 200;

/** What the player wrote, and whether the log goes with it; [requestId] names this draft's sends (server 1.3.0 on). */
export interface FeedbackDraft { text: string; contact: string; log: boolean; requestId?: string }
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
  const body: FeedbackBody & { requestId?: string } = {
    text: draft.text.trim().slice(0, FEEDBACK_TEXT_MAX),
    contact: draft.contact.trim().slice(0, FEEDBACK_CONTACT_MAX),
    system: navigator.userAgent.slice(0, SYSTEM_MAX),
    log,
    ...(draft.requestId ? { requestId: draft.requestId } : {}),
  };
  const r = await attempt((api) => api.feedback(body));
  if (r?.ok) return { ok: true, left: r.value.left };
  // The server's own words for a refusal (the day's limit); anything else is the network or the server.
  const e = r?.error;
  return { ok: false, message: e instanceof ApiError && e.status >= 400 && e.status < 500 && e.code !== "http_error" ? e.message : FAILED };
}

/** The send that is out, with its draft; null when none. */
export const feedbackSending = shallowRef<{ draft: FeedbackDraft; result: Promise<FeedbackResult> } | null>(null);
/** The request id of the last draft sent that did not go through. */
let named: { text: string; contact: string; log: boolean; id: string } | null = null;

function requestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Sends [draft] unless a send is out, which it answers with instead. A draft sent again after a failure keeps its
 *  request id; once one goes through, the settings forget it (what was typed since stays). */
export function submitFeedback(draft: FeedbackDraft): Promise<FeedbackResult> {
  const out = feedbackSending.value;
  if (out) return out.result;
  const same = named && named.text === draft.text && named.contact === draft.contact && named.log === draft.log;
  if (!same) named = { text: draft.text, contact: draft.contact, log: draft.log, id: requestId() };
  const sending = { ...draft, requestId: named!.id };
  const result = sendFeedback(sending).then((r) => {
    if (r.ok) {
      named = null;
      if (settings.feedbackText === draft.text) settings.feedbackText = "";
      if (settings.feedbackContact === draft.contact) settings.feedbackContact = "";
    }
    return r;
  }).finally(() => {
    if (feedbackSending.value?.result === result) feedbackSending.value = null;
  });
  feedbackSending.value = { draft: sending, result };
  return result;
}
