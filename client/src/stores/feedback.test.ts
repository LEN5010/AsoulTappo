import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createSSRApp, ssrContextKey } from "vue";
import { TERMS_VERSION } from "../legal";
import { APP_VERSION } from "../version";

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {} });
});
afterEach(() => vi.unstubAllGlobals());

async function setup(answer: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const posted: unknown[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    if (url.endsWith("/api/feedback")) posted.push(JSON.parse(init.body as string));
    return answer(url, init);
  }));
  const { settings } = await import("./settings");
  settings.serverUrl = "http://a";
  settings.termsAgreed = TERMS_VERSION;
  settings.statementSeen = APP_VERSION;
  return { feedback: await import("./feedback"), posted };
}
const reply = (status: number, data: unknown) => ({ ok: status < 400, status, json: async () => data }) as Response;

it("sends the text and contact trimmed, without a log outside the desktop app", async () => {
  const { feedback, posted } = await setup(() => reply(200, { id: 7, left: 4 }));
  expect(await feedback.sendFeedback({ text: "  背包在抖  ", contact: " QQ 1 ", log: true })).toEqual({ ok: true, left: 4 });
  expect(posted).toEqual([{ text: "背包在抖", contact: "QQ 1", system: expect.any(String), log: "" }]);
});

it("shows the server's words for a refusal and a plain line for anything else", async () => {
  const limit = { detail: { code: "feedback_limit", message: "今天的反馈次数用完了，明天再来吧" } };
  let { feedback } = await setup(() => reply(429, limit));
  expect(await feedback.sendFeedback({ text: "x", contact: "", log: false }))
    .toEqual({ ok: false, message: "今天的反馈次数用完了，明天再来吧" });
  vi.resetModules();
  ({ feedback } = await setup(() => { throw new TypeError("offline"); }));
  expect(await feedback.sendFeedback({ text: "x", contact: "", log: false }))
    .toEqual({ ok: false, message: "发送失败，请检查网络后再试" });
  vi.resetModules();
  ({ feedback } = await setup(() => reply(502, "bad gateway")));
  expect(await feedback.sendFeedback({ text: "x", contact: "", log: false }))
    .toEqual({ ok: false, message: "发送失败，请检查网络后再试" });
});

type Dialog = { send: () => Promise<void>; ready: { value: boolean } };
/** The dialog's own setup and handlers, without a page; [sent] gets what each `sent` event carried. */
async function dialog(sent: number[]): Promise<() => Dialog> {
  const { default: FeedbackDialog } = await import("../panel/FeedbackDialog.vue");
  const app = createSSRApp({});
  app.provide(ssrContextKey, {});
  const setup = (FeedbackDialog as unknown as { setup: (props: object, ctx: object) => Dialog }).setup;
  const emit = (event: string, left?: number) => { if (event === "sent") sent.push(left!); };
  return () => app.runWithContext(() => setup({}, { expose() {}, emit }));
}

it("sends a draft once while it is out, and a dialog opened again follows that send", async () => {
  let answer!: (r: Response) => void;
  const { feedback, posted } = await setup(() => new Promise<Response>((done) => { answer = done; }));
  const { settings } = await import("./settings");
  settings.feedbackText = "背包在抖";
  const sent: number[] = [];
  const open = await dialog(sent);
  const first = open();
  const going = first.send();
  await vi.waitFor(() => expect(posted).toHaveLength(1));
  // The panel hid (the dialog went away) and the player opens it again while the send is out.
  const again = open();
  expect(again.ready.value).toBe(false);
  await again.send();
  expect(await Promise.race([feedback.submitFeedback({ text: "背包在抖", contact: "", log: false }), 0])).toBe(0);
  answer(reply(200, { id: 7, left: 3 }));
  await going;
  await vi.waitFor(() => expect(sent).toEqual([3, 3]));
  expect(posted).toHaveLength(1);
  expect(settings.feedbackText).toBe("");
  expect(again.ready.value).toBe(false);
});

it("names a draft with one request id until a send of it goes through", async () => {
  let fail = true;
  const { feedback, posted } = await setup(() => {
    if (fail) throw new TypeError("offline");
    return reply(200, { id: 7, left: 3 });
  });
  const draft = { text: "背包在抖", contact: "", log: false };
  expect((await feedback.submitFeedback(draft)).ok).toBe(false);
  fail = false;
  expect(await feedback.submitFeedback(draft)).toEqual({ ok: true, left: 3 });
  const ids = posted.map((body) => (body as { requestId?: string }).requestId);
  expect(ids[0]).toMatch(/^[0-9a-f]{32}$/);
  expect(ids[1]).toBe(ids[0]);
  await feedback.submitFeedback(draft);
  await feedback.submitFeedback({ ...draft, text: "表情在抖" });
  const later = posted.slice(2).map((body) => (body as { requestId?: string }).requestId);
  expect(new Set([ids[0], ...later]).size).toBe(3);
});
