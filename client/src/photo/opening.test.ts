// How a box goes on under presses: the table's run without a canvas, its clock pushed on by hand.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { seriesArt } from "./art";
import type { GL } from "./gl";
import type { Kit } from "./kit";
import { createOpening, type Opening, type OpeningEvent } from "./opening";
import type { Painter } from "./painter";
import type { PhotoSound } from "./sound";

const quiet: PhotoSound = {
  load() {}, wake() {}, tick() {}, snap() {}, rustle() {}, slide() {}, flip() {}, thud() {}, lid() {},
};
const there = { ready: Promise.resolve() };
const kit = {
  load: () => Promise.resolve(),
  thumbs: () => ({ drawn: true, ready: Promise.resolve(), rect: () => [0, 0, 1, 1] }),
  want: () => there,
  letGo() {},
} as unknown as Kit;
const gl = { getError: () => 0 } as unknown as GL;

type Told = [number, OpeningEvent][];
/** "sign:bella-2" is the signed bella-2. [woken] is set by every event, as the host wakes the canvas for each. */
function table(
  cards: string[], skipIntro = true, { kit: k = kit, painter = {} as Painter, gl: g = gl, rest = undefined as boolean | undefined } = {},
): { o: Opening; told: Told; woken: { on: boolean } } {
  const told: Told = [], woken = { on: false };
  const deal = cards.map((c) => ({ card: c.replace(/^sign:/, ""), signed: c.startsWith("sign:") }));
  const o: Opening = createOpening(g, k, painter, {
    art: seriesArt("asoul2026")!, deal, skipIntro, ...(rest === undefined ? {} : { rest }), sound: quiet, seed: 1,
    on: (e) => { told.push([o.clock, e]); woken.on = true; },
  });
  return { o, told, woken };
}
/** Frames go by until [done] holds; how long that took. */
async function until(o: Opening, done: () => boolean, most = 20000): Promise<number> {
  const from = o.clock;
  while (!done()) {
    if (o.clock - from > most) throw new Error(`not within ${most} ms`);
    o.update(16);
    await vi.advanceTimersByTimeAsync(0);
  }
  return o.clock - from;
}
const idle = (o: Opening, ms: number) => until(o, () => false, ms).catch(() => undefined);
const sealed = (o: Opening, i: number) => () => o.state().active?.i === i && o.state().active?.state === "sealed";
const out = (o: Opening, card: string) => () => o.state().shown === card;
const told = (list: Told, type: "shown" | "kept", index: number) => () =>
  list.some(([, e]) => e.type === type && e.index === index);
const keptOrder = (list: Told) => list.flatMap(([, e]) => (e.type === "kept" ? [e.index] : []));
const PLAIN = ["diana-1", "bella-2", "eileen-3", "diana-4"];
const MIXED = ["diana-1", "bella-diana-1", "eileen-3", "sign:bella-2", "group-2", "diana-4"];

describe("a box opened by presses", () => {
  // Only for what was waited on to go on between frames: the table keeps its own time.
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("sends a plain card on at once, however far it has turned", async () => {
    const { o, told: list } = table(PLAIN);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, out(o, "diana-1"));
    o.press();
    expect(await until(o, told(list, "kept", 0))).toBeLessThanOrEqual(16);
    expect(told(list, "shown", 0)()).toBe(false);
  });

  it("has the next bag ready to tear soon after a plain card is sent on", async () => {
    const { o } = table(PLAIN);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, out(o, "diana-1"));
    o.press();
    expect(await until(o, sealed(o, 1))).toBeLessThan(300);
    // The press that sent the card on does not tear it as well.
    await idle(o, 1000);
    expect(o.state().active).toMatchObject({ i: 1, state: "sealed", n: 0 });
  });

  it("lets a plain card turn over first when the press came before it was out, then sends it on", async () => {
    const { o, told: list } = table(PLAIN);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, () => list.some(([, e]) => e.type === "torn"));
    o.press();
    await until(o, told(list, "shown", 0));
    expect(await until(o, told(list, "kept", 0))).toBeLessThanOrEqual(32);
  });

  it("lets a plain card turn over while a key is held down", async () => {
    const { o, told: list } = table(PLAIN);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, out(o, "diana-1"));
    o.press(true);
    await until(o, told(list, "shown", 0));
    expect(await until(o, told(list, "kept", 0))).toBeLessThanOrEqual(32);
  });

  it("keeps a plain card on show until a press when none came", async () => {
    const { o, told: list } = table(PLAIN);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, told(list, "shown", 0));
    await idle(o, 3000);
    expect(told(list, "kept", 0)()).toBe(false);
    o.press();
    expect(await until(o, told(list, "kept", 0))).toBeLessThanOrEqual(32);
  });

  it("goes through a box of plain and rare cards, a press for each tear and each card", async () => {
    const { o, told: list } = table(MIXED);
    for (let i = 0; i < MIXED.length; i++) {
      await until(o, sealed(o, i));
      o.press();
      await until(o, told(list, "shown", i));
      o.press();
      await until(o, told(list, "kept", i));
    }
    await until(o, () => o.state().phase === "end");
    expect(keptOrder(list)).toEqual(MIXED.map((_, i) => i));
  });

  it("goes through the same box by itself", async () => {
    const { o, told: list } = table(MIXED);
    await until(o, sealed(o, 0));
    o.setAuto(true);
    await until(o, () => o.state().phase === "end", 60000);
    expect(keptOrder(list)).toEqual(MIXED.map((_, i) => i));
  });
});

/** Time goes by as the engine draws: a frame while the table is busy or was woken, none otherwise. Frames drawn. */
async function engine(o: Opening, woken: { on: boolean }, ms: number): Promise<number> {
  let drawn = 0;
  for (let t = 0; t < ms; t += 16) {
    if (o.busy || woken.on) {
      woken.on = false;
      o.update(16);
      drawn++;
    }
    await vi.advanceTimersByTimeAsync(16);
  }
  return drawn;
}
const stirs = (list: Told, from: number) => list.filter(([at, e]) => e.type === "stir" && at >= from).length;

describe("a table waiting for a hand, when it may stand still", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("stops asking for frames while the box waits, and wakes for each stir of the lid", async () => {
    const { o, told: list, woken } = table(["diana-1"], false, { rest: true });
    await until(o, () => o.state().phase === "intro");
    await engine(o, woken, 6000);
    const from = o.clock, drawn = await engine(o, woken, 60000);
    expect(o.state().phase).toBe("intro");
    expect(drawn).toBeLessThan(3750 * 0.6);
    // The lid stirs every three seconds or so, each time woken for.
    expect(stirs(list, from)).toBeGreaterThanOrEqual(15);
  });

  it("asks for fewer frames while waiting for the first press, frame by frame", async () => {
    const { o } = table(["diana-1"], false, { rest: true });
    for (let f = 0; f < 300; f++) { o.update(1000 / 60); await vi.advanceTimersByTimeAsync(0); }
    expect(o.state().phase).toBe("intro");
    let active = 0;
    for (let f = 0; f < 3600; f++) {
      if (o.busy) active++;
      o.update(1000 / 60);
      await Promise.resolve();
    }
    expect(o.state().phase).toBe("intro");
    expect(active).toBeLessThan(3600 * 0.6);
  });

  it("wakes at once for the pointer and for a key", async () => {
    const { o, woken } = table(["diana-1"], false, { rest: true });
    await until(o, () => o.state().phase === "intro");
    await engine(o, woken, 8000);
    await until(o, () => !o.busy, 4000);
    o.move(40, 20, 0);
    expect(o.busy).toBe(true);
    // The table goes on moving for a while after it.
    expect(await engine(o, woken, 1000)).toBeGreaterThan(55);
    await until(o, () => !o.busy, 8000);
    o.press();
    expect(o.busy).toBe(true);
    await until(o, () => o.state().phase === "play");
  });

  it("stops while a sealed bag waits to be torn, its hint still coming round", async () => {
    const { o, told: list, woken } = table(PLAIN, true, { rest: true });
    await until(o, sealed(o, 0));
    await engine(o, woken, 6000);
    const from = o.clock, drawn = await engine(o, woken, 42000);
    expect(o.state().active).toMatchObject({ i: 0, state: "sealed", n: 0 });
    expect(drawn).toBeLessThan(2625 * 0.6);
    // Every 2.1 s.
    expect(stirs(list, from)).toBeGreaterThanOrEqual(18);
    o.press();
    await until(o, told(list, "shown", 0));
  });

  it("stops altogether while a card waits on show, and goes on with a press", async () => {
    const { o, told: list, woken } = table(PLAIN, true, { rest: true });
    await until(o, sealed(o, 0));
    o.press();
    await until(o, told(list, "shown", 0));
    await engine(o, woken, 8000);
    expect(await engine(o, woken, 20000)).toBe(0);
    o.press();
    expect(await until(o, told(list, "kept", 0))).toBeLessThanOrEqual(32);
  });

  it("does not stand still while the pictures of the next card are still on their way", async () => {
    const slow = { ...kit, want: () => ({ ready: new Promise<void>((done) => setTimeout(done, 6000)) }) } as unknown as Kit;
    const { o, woken } = table(PLAIN, true, { kit: slow, rest: true });
    for (let t = 0; t < 30000 && !sealed(o, 0)(); t += 2000) await engine(o, woken, 2000);
    expect(o.state().active).toMatchObject({ i: 0, state: "sealed" });
  });

  it("never stands still unless asked to: every frame is wanted and nothing slows", async () => {
    // Whatever is asked of these does nothing; the painter keeps the clock it is given.
    let painted = -1;
    const any = <T>(o: object) => new Proxy(o, { get: (t, k) => (k in t ? Reflect.get(t, k) : () => undefined) }) as T;
    for (const [cards, intro] of [[["diana-1"], false], [PLAIN, true]] as const) {
      const { o, told: list } = table([...cards], intro, {
        painter: any<Painter>({ blended: "over", begin: (f: { clock: number }) => { painted = f.clock; } }),
        gl: any<GL>({ drawingBufferWidth: 960, drawingBufferHeight: 640, getError: () => 0 }),
      });
      o.resize(960, 640, 1);
      await until(o, intro ? sealed(o, 0) : () => o.state().phase === "intro");
      const from = o.clock;
      for (let f = 0; f < 3750; f++) {
        expect(o.busy).toBe(true);
        o.update(16);
        o.draw();
        await vi.advanceTimersByTimeAsync(16);
      }
      expect(o.state().phase).toBe(intro ? "play" : "intro");
      // What sways by itself went by the table's own clock the whole time.
      expect(painted).toBe(o.clock);
      expect(o.clock - from).toBe(60000);
      expect(stirs(list, 0)).toBe(0);
    }
  });

  it("keeps drawing while the box opens by itself", async () => {
    const { o, woken } = table(PLAIN, true, { rest: true });
    await until(o, sealed(o, 0));
    o.setAuto(true);
    expect(await engine(o, woken, 3000)).toBeGreaterThan(180);
  });
});

const tornAfter = (list: Told, from: number) => list.filter(([at, e]) => e.type === "torn" && at > from).length;
const inHand = (o: Opening, i: number, state: string) => () => o.state().active?.i === i && o.state().active?.state === state;
/** Presses go on through each rare card as it comes; the run up to the end, and how many presses it took. */
async function pressThrough(o: Opening, list: Told, rare: number[]): Promise<void> {
  for (const i of rare) {
    // Each is taken up sealed, torn by itself and turned over in the dark, and waits on show for a press.
    await until(o, inHand(o, i, "sealed"));
    await until(o, told(list, "shown", i));
    expect(o.state().spot).toBe(o.state().deal[i]);
    await idle(o, 1500);
    expect(told(list, "kept", i)()).toBe(false);
    o.press();
    await until(o, told(list, "kept", i));
  }
}

describe("a box skipped through", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("sends the cards of one member down at once and opens each rare one as it would have been", async () => {
    const { o, told: list } = table(MIXED);
    await until(o, sealed(o, 0));
    const at = o.clock;
    expect(o.skip()).toBe("rush");
    // The plain ones go to the row first, without a press, left to right.
    expect(await until(o, () => [0, 2, 5].every((i) => told(list, "kept", i)()), 4000)).toBeLessThan(2500);
    expect(keptOrder(list)).toEqual([0, 2, 5]);
    expect(list.some(([, e]) => e.type === "shown" && [0, 2, 5].includes(e.index))).toBe(false);
    await pressThrough(o, list, [1, 3, 4]);
    await until(o, () => o.state().phase === "end", 6000);
    expect(keptOrder(list)).toEqual([0, 2, 5, 1, 3, 4]);
    // The box counted as opened at the skip: nothing more is told torn.
    expect(tornAfter(list, at)).toBe(0);
  });

  it("lays the whole box out on a second skip while a rare card is on its way", async () => {
    const { o, told: list } = table(MIXED);
    await until(o, sealed(o, 0));
    o.skip();
    await until(o, told(list, "shown", 1));
    expect(o.skip()).toBe("all");
    expect(await until(o, () => o.state().phase === "end", 6000)).toBeLessThan(3000);
    expect(told(list, "shown", 3)()).toBe(false);
  });

  it("ends by itself when no rare card is left", async () => {
    const { o, told: list } = table(PLAIN);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, told(list, "shown", 0));
    expect(o.skip()).toBe("rush");
    // The one on show goes down at once.
    expect(await until(o, told(list, "kept", 0))).toBeLessThanOrEqual(16);
    expect(await until(o, () => o.state().phase === "end", 8000)).toBeLessThan(5000);
    expect(keptOrder(list)).toEqual([0, 1, 2, 3]);
  });

  it("lets a rare card on show finish before the row comes", async () => {
    const { o, told: list } = table(MIXED);
    await until(o, sealed(o, 0));
    o.press();
    await until(o, told(list, "shown", 0));
    o.press();
    await until(o, sealed(o, 1));
    o.press();
    await until(o, told(list, "shown", 1));
    expect(o.skip()).toBe("rush");
    await idle(o, 1500);
    expect(told(list, "kept", 1)()).toBe(false);
    o.press();
    await until(o, () => [1, 2, 5].every((i) => told(list, "kept", i)()), 5000);
    await pressThrough(o, list, [3, 4]);
    await until(o, () => o.state().phase === "end", 6000);
    expect(keptOrder(list)).toEqual([0, 1, 2, 5, 3, 4]);
  });

  it("goes through a skipped box by itself while it opens by itself", async () => {
    const { o, told: list } = table(MIXED);
    await until(o, sealed(o, 0));
    o.setAuto(true);
    expect(o.skip()).toBe("rush");
    await until(o, () => o.state().phase === "end", 30000);
    expect(keptOrder(list)).toEqual([0, 2, 5, 1, 3, 4]);
  });

  it("goes out with what is left on the desk when closed while a skipped box is still showing", async () => {
    const { o, told: list } = table(MIXED);
    await until(o, sealed(o, 0));
    o.skip();
    await until(o, told(list, "shown", 1));
    let gone = false;
    void o.goOut().then(() => { gone = true; });
    await until(o, () => gone, 3000);
    expect(o.state().phase).toBe("leaving");
    expect(told(list, "kept", 1)()).toBe(false);
  });

  it("draws the row of a skipped box", async () => {
    // Whatever is asked of these does nothing.
    const any = <T>(o: object) => new Proxy(o, { get: (t, k) => (k in t ? Reflect.get(t, k) : () => undefined) }) as T;
    const { o, told: list } = table(MIXED, true, {
      painter: any<Painter>({ blended: "over" }),
      gl: any<GL>({ drawingBufferWidth: 960, drawingBufferHeight: 640, getError: () => 0 }),
    });
    o.resize(960, 640, 1);
    await until(o, sealed(o, 0));
    o.skip();
    let frames = 0;
    await until(o, () => {
      o.draw();
      frames++;
      if (told(list, "shown", 1)()) o.press();
      if (told(list, "shown", 3)()) o.press();
      if (told(list, "shown", 4)()) o.press();
      return o.state().phase === "end";
    }, 40000);
    expect(frames).toBeGreaterThan(100);
  });

  it("lays everything out at once when skipped before the box is open", async () => {
    const { o } = table(MIXED, false);
    await until(o, () => o.state().phase === "intro");
    expect(o.skip()).toBe("all");
    await until(o, () => o.state().phase === "end", 6000);
  });
});
