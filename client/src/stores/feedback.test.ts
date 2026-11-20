import { afterEach, beforeEach, expect, it, vi } from "vitest";
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
