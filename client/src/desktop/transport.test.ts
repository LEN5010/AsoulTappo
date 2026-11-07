import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { emitTo, listen } from "@tauri-apps/api/event";
import { DESKTOP_REQUEST_TIMEOUT_MS, requestDesktop } from "./transport";

const mock = vi.hoisted(() => ({ stop: vi.fn(), handler: undefined as ((event: { payload: unknown }) => void) | undefined }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(), emitTo: vi.fn() }));
beforeEach(() => {
  vi.useFakeTimers();
  mock.stop.mockReset();
  mock.handler = undefined;
  vi.mocked(listen).mockImplementation(async (_event, handler) => {
    mock.handler = handler as (event: { payload: unknown }) => void;
    return mock.stop;
  });
  vi.mocked(emitTo).mockResolvedValue(undefined);
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.restoreAllMocks(); });

it("cleans up after a successful reply", async () => {
  const result = requestDesktop<string>("createRoom");
  await Promise.resolve();
  mock.handler!({ payload: { result: "room" } });
  expect(await result).toBe("room");
  expect(mock.stop).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});
it("rejects a lost reply and does not resend a mutation", async () => {
  const result = requestDesktop("resonate", 10);
  const rejected = expect(result).rejects.toThrow("响应超时");
  await vi.advanceTimersByTimeAsync(DESKTOP_REQUEST_TIMEOUT_MS);
  await rejected;
  expect(mock.stop).toHaveBeenCalledTimes(1);
  expect(emitTo).toHaveBeenCalledTimes(1);
  mock.handler!({ payload: { result: [] } });
  expect(mock.stop).toHaveBeenCalledTimes(1);
});
it("cleans up when sending fails", async () => {
  vi.mocked(emitTo).mockRejectedValueOnce(new Error("closed"));
  await expect(requestDesktop("sync")).rejects.toThrow("closed");
  expect(mock.stop).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});
it("cleans a listener that registers after the request expired", async () => {
  let register!: (stop: () => void) => void;
  vi.mocked(listen).mockImplementationOnce(() => new Promise((resolve) => { register = resolve; }));
  const result = requestDesktop("sync");
  const rejected = expect(result).rejects.toThrow("响应超时");
  await vi.advanceTimersByTimeAsync(DESKTOP_REQUEST_TIMEOUT_MS);
  await rejected;
  register(mock.stop);
  await Promise.resolve();
  expect(mock.stop).toHaveBeenCalledTimes(1);
  expect(emitTo).not.toHaveBeenCalled();
});
it("rejects a reply error and removes its timer", async () => {
  const result = requestDesktop("craftItem", "card");
  await Promise.resolve();
  mock.handler!({ payload: { error: "not owned" } });
  await expect(result).rejects.toThrow("not owned");
  expect(mock.stop).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("clears its deadline when listener registration fails", async () => {
  vi.mocked(listen).mockRejectedValueOnce(new Error("listener failed"));
  await expect(requestDesktop("sync")).rejects.toThrow("listener failed");
  expect(vi.getTimerCount()).toBe(0);
  expect(emitTo).not.toHaveBeenCalled();
});
it("still times out if sending never settles", async () => {
  vi.mocked(emitTo).mockImplementationOnce(() => new Promise(() => {}));
  const result = requestDesktop("joinRoom", "abc");
  const rejected = expect(result).rejects.toThrow("响应超时");
  await vi.advanceTimersByTimeAsync(DESKTOP_REQUEST_TIMEOUT_MS);
  await rejected;
  expect(mock.stop).toHaveBeenCalledTimes(1);
});
