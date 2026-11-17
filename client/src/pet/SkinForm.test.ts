import { describe, expect, it } from "vitest";
import { SkinForm } from "./SkinForm";
import type { Timers } from "./EmotePlayer";

/** Manual clock: timers fire when `advance` passes them. */
function clock() {
  let now = 0;
  let seq = 0;
  const due = new Map<number, { at: number; cb: () => void }>();
  const timers: Timers = {
    set: (cb, ms) => { const id = ++seq; due.set(id, { at: now + ms, cb }); return id; },
    clear: (h) => { due.delete(h as number); },
  };
  const advance = (ms: number) => {
    const end = now + ms;
    for (;;) {
      const next = [...due.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      due.delete(next[0]);
      now = next[1].at;
      next[1].cb();
    }
    now = end;
  };
  return { timers, advance, get now() { return now; } };
}

const RULES = { holdMs: 4000, gapMs: 1500, restMs: 3000 };

function typing(form: SkinForm, c: ReturnType<typeof clock>, ms: number, every = 200) {
  for (let t = 0; t < ms; t += every) { form.press(c.now); c.advance(every); }
}

describe("two-form skins", () => {
  it("change after four seconds of typing and back after three idle", () => {
    const c = clock();
    const seen: boolean[] = [];
    const form = new SkinForm((on) => seen.push(on), RULES, c.timers);
    typing(form, c, 3800);
    expect(form.on).toBe(false);
    typing(form, c, 600);
    expect(form.on).toBe(true);
    // the last press was 200ms ago
    c.advance(2700);
    expect(form.on).toBe(true);
    c.advance(200);
    expect(form.on).toBe(false);
    expect(seen).toEqual([true, false]);
  });

  it("start over after a pause longer than the gap", () => {
    const c = clock();
    const form = new SkinForm(() => {}, RULES, c.timers);
    typing(form, c, 3000);
    c.advance(1600);
    typing(form, c, 3000);
    expect(form.on).toBe(false);
  });

  it("stay changed through short pauses", () => {
    const c = clock();
    const form = new SkinForm(() => {}, RULES, c.timers);
    typing(form, c, 4400);
    expect(form.on).toBe(true);
    for (let i = 0; i < 4; i++) { c.advance(2500); form.press(c.now); }
    expect(form.on).toBe(true);
  });

  it("go back at once on reset", () => {
    const c = clock();
    const seen: boolean[] = [];
    const form = new SkinForm((on) => seen.push(on), RULES, c.timers);
    typing(form, c, 4400);
    form.reset();
    c.advance(5000);
    expect(seen).toEqual([true, false]);
  });
});
