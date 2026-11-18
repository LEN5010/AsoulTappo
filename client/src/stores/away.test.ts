import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AWAY_AFTER_MS, AwayClock } from "../away";
import { noteAwayInput, shownStatus, startAway } from "./away";
import { settings } from "./settings";

describe("AwayClock", () => {
  it("is away once there has been no input for the whole stretch", () => {
    const clock = new AwayClock(1000);
    expect(clock.away(1000 + AWAY_AFTER_MS - 1)).toBe(false);
    expect(clock.away(1000 + AWAY_AFTER_MS)).toBe(true);
    clock.input(1000 + AWAY_AFTER_MS);
    expect(clock.away(1000 + AWAY_AFTER_MS + 1)).toBe(false);
  });
});

describe("the status shown to the room", () => {
  let stop: () => void;
  beforeEach(() => {
    vi.useFakeTimers();
    settings.status = "work";
    stop = startAway();
  });
  afterEach(() => {
    stop();
    settings.status = "";
    vi.useRealTimers();
  });

  it("turns to away after a while without input and back to the chosen one on input", () => {
    expect(shownStatus.value).toBe("work");
    vi.advanceTimersByTime(AWAY_AFTER_MS + 15_000);
    expect(shownStatus.value).toBe("away");
    noteAwayInput({ kind: "mouse_move", dx: 1, dy: 0 });
    expect(shownStatus.value).toBe("work");
  });

  it("stays away through presses other software sent", () => {
    vi.advanceTimersByTime(AWAY_AFTER_MS + 15_000);
    noteAwayInput({ kind: "key_down", injected: true });
    expect(shownStatus.value).toBe("away");
    noteAwayInput({ kind: "key_down", injected: false });
    expect(shownStatus.value).toBe("work");
  });

  it("keeps a status that says there may be no input, and one chosen as away", () => {
    settings.status = "live";
    vi.advanceTimersByTime(AWAY_AFTER_MS + 15_000);
    expect(shownStatus.value).toBe("live");
    settings.status = "away";
    noteAwayInput({ kind: "key_down" });
    expect(shownStatus.value).toBe("away");
  });

  it("shows no status as away too", () => {
    settings.status = "";
    vi.advanceTimersByTime(AWAY_AFTER_MS + 15_000);
    expect(shownStatus.value).toBe("away");
  });
});
