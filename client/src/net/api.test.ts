import { describe, expect, it, vi } from "vitest";
import { Api, ActivityReporter, ApiError, newToken, seriesProgress } from "./api";

const resp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);

describe("Api", () => {
  it("sends the token header and json body", async () => {
    const f = vi.fn(() => resp(200, { shards: 1600 }));
    const api = new Api(() => "http://h:1/", () => "tok", f);
    const batch = { taps: 7, session: "s".repeat(24), sequence: 1 };
    await api.activity(batch);
    expect(f).toHaveBeenCalledWith("http://h:1/api/activity", expect.objectContaining({
      method: "POST", body: JSON.stringify(batch),
      headers: expect.objectContaining({ "X-Player-Token": "tok", "Content-Type": "application/json" }),
    }));
  });
  it("posts only the count to the unified resonance route", async () => {
    const f = vi.fn(() => resp(200, { drops: [] }));
    const api = new Api(() => "http://h", () => "tok", f);
    await api.resonate(10);
    expect(f).toHaveBeenCalledWith("http://h/api/resonance/draw", expect.objectContaining({ method: "POST", body: JSON.stringify({ count: 10 }) }));
  });
  it("turns server errors into ApiError with the code", async () => {
    const api = new Api(() => "http://h", () => "t", () => resp(409, { detail: { code: "no_shards", message: "碎片不足" } }));
    await expect(api.resonate()).rejects.toMatchObject({ status: 409, code: "no_shards", message: "碎片不足" });
    const api2 = new Api(() => "http://h", () => "t", () => resp(500, "x"));
    await expect(api2.me()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("ActivityReporter", () => {
  it("retries the committed batch identity without crediting new input twice", async () => {
    const seen = new Set<string>();
    let credited = 0;
    let first = true;
    const r = new ActivityReporter(async (batch) => {
      const key = `${batch.session}:${batch.sequence}`;
      if (!seen.has(key)) { seen.add(key); credited += batch.taps; }
      if (first) { first = false; throw new TypeError("response lost"); }
    });
    r.add(10);
    expect(await r.flush()).toBe(false);
    r.add(2);
    expect(await r.flush()).toBe(true);
    expect(credited).toBe(10);
    expect(await r.flush()).toBe(true);
    expect(credited).toBe(12);
  });
  it("concurrent flushes await the same request", async () => {
    let release!: () => void;
    const send = vi.fn(() => new Promise<void>((resolve) => { release = resolve; }));
    const r = new ActivityReporter(send);
    r.add(10);
    const a = r.flush();
    const b = r.flush();
    expect(a).toBe(b);
    release();
    expect(await b).toBe(true);
    expect(send).toHaveBeenCalledTimes(1);
  });
  it("batches counts and keeps them when sending fails", async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValue(undefined);
    const r = new ActivityReporter(send);
    r.add(); r.add(4);
    expect(await r.flush()).toBe(false);
    expect(r.size).toBe(5);
    r.add(2);
    expect(await r.flush()).toBe(true);
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ taps: 5, sequence: 1 }));
    expect(r.size).toBe(2);
    expect(await r.flush()).toBe(true);
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ taps: 2, sequence: 2 }));
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
