import { beforeEach, describe, expect, it, vi } from "vitest";
import { autoHint, autoNote, closeAutoHint, noteAutoInput, openAutoNote } from "./autoHint";

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
  });

  it("goes up when the status says so and stays until closed", () => {
    noteAutoInput(undefined, noon);
    noteAutoInput(0, noon);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, noon);
    expect(autoHint.value).toBe(true);
    // The status no longer says so: the note is still there for the player to read.
    noteAutoInput(0, noon + 3_600_000);
    expect(autoHint.value).toBe(true);
  });

  it("opens the note behind the bubble, and closing the note puts both away", () => {
    openAutoNote();
    expect(autoNote.value).toBe(false);
    noteAutoInput(1800, noon);
    openAutoNote();
    expect([autoHint.value, autoNote.value]).toEqual([true, true]);
    closeAutoHint(noon);
    expect([autoHint.value, autoNote.value]).toEqual([false, false]);
  });

  it("comes once a day", () => {
    noteAutoInput(1800, noon);
    closeAutoHint(noon);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, noon + 3_600_000);
    expect(autoHint.value).toBe(false);
    noteAutoInput(1800, noon + DAY);
    expect(autoHint.value).toBe(true);
  });
});
