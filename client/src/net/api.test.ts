import { describe, expect, it, vi } from "vitest";
import { Api, ActivityReporter, ApiError, newToken, seriesProgress } from "./api";

const resp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);

describe("Api", () => {
  it("sends the token header and json body", async () => {
    const f = vi.fn(() => resp(200, { boxes: 1 }));
    const api = new Api(() => "http://h:1/", () => "tok", f);
    await api.activity(7);
    expect(f).toHaveBeenCalledWith("http://h:1/api/activity", expect.objectContaining({
      method: "POST", body: JSON.stringify({ taps: 7 }),
      headers: expect.objectContaining({ "X-Player-Token": "tok", "Content-Type": "application/json" }),
    }));
  });
  it("turns server errors into ApiError with the code", async () => {
    const api = new Api(() => "http://h", () => "t", () => resp(409, { detail: { code: "no_box", message: "没有宝箱" } }));
    await expect(api.openBox()).rejects.toMatchObject({ status: 409, code: "no_box", message: "没有宝箱" });
    const api2 = new Api(() => "http://h", () => "t", () => resp(500, "x"));
    await expect(api2.me()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("ActivityReporter", () => {
  it("batches counts and keeps them when sending fails", async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValue(undefined);
    const r = new ActivityReporter(send);
    r.add(); r.add(4);
    expect(await r.flush()).toBe(false);
    expect(r.size).toBe(5);
    r.add(2);
    expect(await r.flush()).toBe(true);
    expect(send).toHaveBeenLastCalledWith(7);
    expect(r.size).toBe(0);
  });
  it("caps the pending count", () => {
    const r = new ActivityReporter(async () => {});
    r.add(10000);
    expect(r.size).toBe(5000);
  });
});

describe("misc", () => {
  it("tokens are long hex and differ", () => {
    const a = newToken();
    expect(a).toMatch(/^[0-9a-f]{48}$/);
    expect(newToken()).not.toBe(a);
  });
  it("seriesProgress counts owned cards per series", () => {
    const p = seriesProgress({});
    expect(p.every((s) => s.have === 0 && s.total > 0)).toBe(true);
  });
});
