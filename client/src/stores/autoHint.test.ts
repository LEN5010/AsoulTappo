import { beforeEach, describe, expect, it, vi } from "vitest";
import { autoHint, autoNote, autoStrikes, closeAutoHint, noteAutoInput, openAutoNote } from "./autoHint";

const DAY = 86_400_000;
const noon = new Date(2026, 10, 17, 12).getTime();

describe("the automatic-input note", () => {
  beforeEach(() => {
    const kept = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => kept.get(key) ?? null,
      setItem: (key: string, value: string) => void kept.set(key, value),
    });
    autoHint.value = false;
    autoNote.value = false;
    autoStrikes.value = 0;
  });

  it("goes up when the status says so and stays until closed", () => {
    noteAutoInput(undefined, 0, noon);
    noteAutoInput(0, 0, noon);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, 0, noon);
    expect(autoHint.value).toBe(true);
    // The status no longer says so: the note is still there for the player to read.
    noteAutoInput(0, 0, noon + 3_600_000);
    expect(autoHint.value).toBe(true);
  });

  it("opens the note behind the bubble, and closing the note puts both away", () => {
    openAutoNote();
    expect(autoNote.value).toBe(false);
    noteAutoInput(1800, 0, noon);
    openAutoNote();
    expect([autoHint.value, autoNote.value]).toEqual([true, true]);
    closeAutoHint(noon);
    expect([autoHint.value, autoNote.value]).toEqual([false, false]);
  });

  it("comes once a day", () => {
    noteAutoInput(1800, 0, noon);
    closeAutoHint(noon);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, 0, noon + 3_600_000);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, 0, noon + DAY);
    expect(autoHint.value).toBe(true);
  });

  it("comes again with each new strike of the day", () => {
    noteAutoInput(1800, 0, noon);
    closeAutoHint(noon);
    noteAutoInput(1800, 1, noon + 1_800_000);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 1]);
    closeAutoHint(noon + 1_800_000);
    noteAutoInput(1800, 1, noon + 2_000_000);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, 2, noon + 3_600_000);
    expect(autoHint.value).toBe(true);
  });

  it("keeps strikes when status clears or autoInput expires while the bubble is still open", () => {
    noteAutoInput(1800, 1, noon);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 1]);
    noteAutoInput(0, 0, noon + 3_600_000);
    noteAutoInput(undefined, undefined, noon + 3_600_000);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 1]);
    closeAutoHint(noon + 3_600_000);
    noteAutoInput(1800, 1, noon + 4_000_000);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, 2, noon + 5_000_000);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 2]);
  });

  it("updates strikes when a new strike arrives while the bubble is already up", () => {
    noteAutoInput(1800, 0, noon);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 0]);
    noteAutoInput(1800, 1, noon + 60_000);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 1]);
    closeAutoHint(noon + 60_000);
    noteAutoInput(1800, 1, noon + 120_000);
    expect(autoHint.value).toBe(false);
  });

  it("does not carry yesterday's strikes into today when a leftover bubble is closed after midnight", () => {
    noteAutoInput(1800, 2, noon);
    noteAutoInput(0, 0, noon + DAY);
    closeAutoHint(noon + DAY);
    noteAutoInput(1800, 1, noon + DAY + 60_000);
    expect([autoHint.value, autoStrikes.value]).toEqual([true, 1]);
  });
});
