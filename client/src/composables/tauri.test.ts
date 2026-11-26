import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const invokeMock = vi.hoisted(() => vi.fn(async (..._args: unknown[]): Promise<unknown> => undefined));
vi.mock("@tauri-apps/api/core", () => ({ invoke: invokeMock }));

async function loadTauri() {
  vi.resetModules();
  vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: "?window=panel" } });
  return import("./tauri");
}

describe("writeLog", () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: 1_000_000 });
    invokeMock.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("folds consecutive repeats within a minute and reports the count when the same line recurs in a new minute", async () => {
    const { writeLog } = await loadTauri();
    const err = "error: ResizeObserver loop completed with undelivered notifications.";

    writeLog("panel", err);
    writeLog("panel", err);
    writeLog("panel", err);
    expect(invokeMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenLastCalledWith("write_log", { tag: "panel", msg: err });

    vi.advanceTimersByTime(60_000);
    writeLog("panel", err);
    expect(invokeMock).toHaveBeenCalledTimes(2);
    expect(invokeMock).toHaveBeenLastCalledWith("write_log", {
      tag: "panel",
      msg: `${err} (2 more since the last line)`,
    });
  });

  it("attaches the skipped repeat count to the next distinct line and resets the counter", async () => {
    const { writeLog } = await loadTauri();

    writeLog("panel", "first");
    writeLog("panel", "first");
    writeLog("panel", "first");
    writeLog("panel", "first");
    expect(invokeMock).toHaveBeenCalledTimes(1);

    writeLog("panel", "second");
    expect(invokeMock).toHaveBeenCalledTimes(2);
    expect(invokeMock).toHaveBeenLastCalledWith("write_log", {
      tag: "panel",
      msg: "second (previous line repeated 3x)",
    });

    writeLog("panel", "third");
    expect(invokeMock).toHaveBeenCalledTimes(3);
    expect(invokeMock).toHaveBeenLastCalledWith("write_log", { tag: "panel", msg: "third" });
  });

  it("preserves accumulated repeat counts when the per-minute cap prevents flushing until the next minute", async () => {
    const { writeLog } = await loadTauri();

    for (let i = 0; i < 29; i += 1) writeLog("panel", `line-${i}`);
    writeLog("panel", "noisy");
    expect(invokeMock).toHaveBeenCalledTimes(30);

    writeLog("panel", "noisy");
    writeLog("panel", "noisy");
    writeLog("panel", "dropped-by-cap");
    expect(invokeMock).toHaveBeenCalledTimes(30);

    vi.advanceTimersByTime(60_000);
    writeLog("panel", "after-cap");
    expect(invokeMock).toHaveBeenCalledTimes(31);
    expect(invokeMock).toHaveBeenLastCalledWith("write_log", {
      tag: "panel",
      msg: "after-cap (previous line repeated 2x)",
    });
  });
});

describe("reading the log back", () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: 1_000_000 });
    invokeMock.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /** Each command once it has finished, with the line it wrote. */
  function recordFinished(): string[] {
    const done: string[] = [];
    invokeMock.mockImplementation(async (...args: unknown[]) => {
      const [name, payload] = args as [string, { msg?: string } | undefined];
      // A write takes a moment: the read that follows waits for it.
      if (name === "write_log") await Promise.resolve();
      done.push(payload?.msg ?? name);
      return name === "log_tail" ? "tail" : undefined;
    });
    return done;
  }

  it("writes the repeats still counted before the log is exported", async () => {
    const done = recordFinished();
    const { writeLog, exportLog } = await loadTauri();
    for (let i = 0; i < 7; i += 1) writeLog("panel", "same rendering error");
    await exportLog();
    expect(done).toEqual([
      "same rendering error",
      "same rendering error (6 more since the last line)",
      "export_log",
    ]);
    expect(invokeMock).toHaveBeenCalledWith("write_log", {
      tag: "panel",
      msg: "same rendering error (6 more since the last line)",
    });
  });

  it("writes them before the tail is read for a feedback, and only once", async () => {
    const done = recordFinished();
    const { writeLog, logTail } = await loadTauri();
    writeLog("panel", "boom");
    writeLog("panel", "boom");
    expect(await logTail()).toBe("tail");
    expect(await logTail()).toBe("tail");
    expect(done).toEqual(["boom", "boom (1 more since the last line)", "log_tail", "log_tail"]);
    // Counted afresh from there.
    writeLog("panel", "boom");
    writeLog("panel", "other");
    expect(invokeMock).toHaveBeenLastCalledWith("write_log", { tag: "panel", msg: "other (previous line repeated 1x)" });
  });

  it("adds nothing when no repeat is counted", async () => {
    const done = recordFinished();
    const { writeLog, exportLog } = await loadTauri();
    writeLog("panel", "once");
    await exportLog();
    expect(done).toEqual(["once", "export_log"]);
  });
});
