import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TapBatcher } from "./TapBatcher";

describe("TapBatcher", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("batches taps within the window into one count", () => {
    const send = vi.fn();
    const b = new TapBatcher(send, 150);
    b.add();
    b.add();
    b.add(3);
    expect(send).not.toHaveBeenCalled();
    vi.advanceTimersByTime(149);
    expect(send).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(send).toHaveBeenCalledExactlyOnceWith(5);
  });

  it("does not send when nothing is pending and starts a new window after a flush", () => {
    const send = vi.fn();
    const b = new TapBatcher(send, 100);
    vi.advanceTimersByTime(1000);
    expect(send).not.toHaveBeenCalled();
    b.add();
    vi.advanceTimersByTime(100);
    b.add(2);
    vi.advanceTimersByTime(100);
    expect(send.mock.calls).toEqual([[1], [2]]);
  });

  it("splits oversized batches to respect the server cap", () => {
    const send = vi.fn();
    const b = new TapBatcher(send, 100, 500);
    b.add(1200);
    b.flush();
    expect(send.mock.calls).toEqual([[500], [500], [200]]);
  });

  it("clear drops pending taps", () => {
    const send = vi.fn();
    const b = new TapBatcher(send, 100);
    b.add(4);
    b.clear();
    vi.advanceTimersByTime(500);
    expect(send).not.toHaveBeenCalled();
  });

  it("ignores non-positive counts", () => {
    const send = vi.fn();
    const b = new TapBatcher(send, 100);
    b.add(0);
    b.add(-3);
    b.flush();
    expect(send).not.toHaveBeenCalled();
  });
});
