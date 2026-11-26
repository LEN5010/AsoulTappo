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
/** "sign:bella-2" is the signed bella-2. */
function table(cards: string[]): { o: Opening; told: Told } {
  const told: Told = [];
  const deal = cards.map((c) => ({ card: c.replace(/^sign:/, ""), signed: c.startsWith("sign:") }));
  const o: Opening = createOpening(gl, kit, {} as Painter, {
    art: seriesArt("asoul2026")!, deal, skipIntro: true, sound: quiet, seed: 1, on: (e) => told.push([o.clock, e]),
  });
  return { o, told };
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
