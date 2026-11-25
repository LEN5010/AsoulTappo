// The shelf without a canvas: that it asks for the frames it needs, and that what is waited for of it comes about.
import { describe, expect, it } from "vitest";
import { seriesArt } from "./art";
import type { GL } from "./gl";
import type { Kit } from "./kit";
import type { Painter } from "./painter";
import { createShelf, type Face } from "./shelf";

const art = seriesArt("asoul2026")!;
const cards: Face[] = art.cards.map((c) => ({ card: c.id, signed: false }));

/** With [slow], pictures are there once load() was called. [told]: the cards that came up. */
async function shelf({ slow = false, place = { x: 0, y: 0, scale: 1 } } = {}) {
  const told: string[] = [];
  let waits: (() => void)[] = [], wait = false;
  const load = () => {
    wait = false;
    waits.forEach((done) => done());
    waits = [];
  };
  const kit = {
    ink: async () => {}, signs: async () => {}, letGoSmall() {},
    small: () => ({ ready: new Promise<void>((done) => { if (wait) waits.push(done); else done(); }) }),
  } as unknown as Kit;
  const rect = () => ({ left: 100, top: 40, width: 480, height: 560 }) as DOMRect;
  const s = createShelf({} as GL, kit, {} as Painter, { art, cards, rect, place: () => place, on: (f) => told.push(f.card) });
  await s.ready;
  wait = slow;
  return { s, load, told };
}
type Shelf = Awaited<ReturnType<typeof shelf>>["s"];
/** Lets what promises have queued run. */
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
/** Frames as the canvas takes them: another one only while something moves. */
async function run(s: Shelf, ms: number): Promise<void> {
  for (let t = 0, busy = true; t < ms && busy; t += 16) {
    s.update(16);
    busy = s.busy;
    await settle();
  }
}
async function settles(p: Promise<void>): Promise<boolean> {
  let done = false;
  void p.then(() => { done = true; });
  await settle();
  return done;
}

describe("the shelf", () => {
  it("brings up another card after it has come to rest", async () => {
    const { s, told } = await shelf();
    s.enter();
    await run(s, 40_000);
    expect(s.busy).toBe(false);
    s.next();
    await run(s, 4000);
    expect(told.length).toBe(2);
    s.down(0, -150, 0);
    expect(s.up()).toMatchObject({ kind: "card", card: told[1] });
  });

  it("goes by the size its host has now, though another view has the canvas", async () => {
    const { s } = await shelf({ place: { x: 30, y: -6, scale: 1.4 } });
    expect(s.place()).toMatchObject({ cx: 370, cy: 314, css: 1.4 });
  });

  it("packs the series on its way once it is here, whatever is told meanwhile", async () => {
    const { s, load } = await shelf({ slow: true });
    s.enter();
    await run(s, 2000);
    s.change(art, cards, 1, null, 20);
    await run(s, 96);
    const packed = s.pack();
    await run(s, 480);
    s.waiting(20, 20);
    load();
    await run(s, 5000);
    expect(await settles(packed)).toBe(true);
  });

  it("lets the series on its way come when it need not be packed after all", async () => {
    const { s } = await shelf();
    s.enter();
    await run(s, 2000);
    s.change(art, cards, 1, null, 20);
    await run(s, 96);
    const packed = s.pack();
    await run(s, 96);
    s.unpack();
    await run(s, 5000);
    expect(await settles(packed)).toBe(true);
    expect(s.hand().cx).toBeCloseTo(340);
  });
});
