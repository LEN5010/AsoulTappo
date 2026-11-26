// The full-size textures of a card looked at: those the viewer no longer shows nor is about to are let go as it pages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { seriesArt, type CardInfo } from "./art";
import type { Face } from "./shelf";

/** Textures made from each picture, and those there are now. */
const io = vi.hoisted(() => ({
  made: new Map<string, number>(), live: new Set<object>(),
  /** A picture that comes once this resolves. */
  late: null as null | { url: string; come: Promise<void> },
}));
vi.mock("./gl", async (actual) => ({
  ...await actual<typeof import("./gl")>(),
  picture: async (url: string) => {
    if (io.late?.url === url) await io.late.come;
    return { width: 4, height: 4, url, close() {} };
  },
  texture: (_gl: unknown, source: { url?: string } | null) => {
    const t = { url: source?.url ?? "" };
    if (t.url) io.made.set(t.url, (io.made.get(t.url) ?? 0) + 1);
    io.live.add(t);
    return t;
  },
  grid: () => ({ draw() {}, dispose() {} }),
  startProgram: () => ({ ready: Promise.resolve(), use() {}, tex() {}, set() {}, dispose() {} }),
}));

const art = seriesArt("asoul2026")!;
const gl = new Proxy({ deleteTexture: (t: object) => io.live.delete(t) } as Record<string, unknown>, {
  get: (target, k) => (k in target ? target[k as string] : () => ({})),
});

async function setup(calm: boolean) {
  const { createKit } = await import("./kit");
  const { createViewer } = await import("./viewer");
  const kit = createKit(gl as never);
  await vi.runAllTimersAsync();
  await kit.ready;
  const signs = kit.signs(art.id);
  await vi.runAllTimersAsync();
  await signs;
  /** What each card drawn was drawn with. */
  const drawn: { card: string; faces: unknown }[] = [];
  const painter = new Proxy({
    card: (m: { info: CardInfo }) => drawn.push({ card: m.info.id, faces: kit.faces(m.info) }),
  } as Record<string, unknown>, { get: (target, k) => (k in target ? target[k as string] : () => {}) });
  const view = createViewer(gl as never, kit, painter as never, {
    art, calm, rect: () => ({ left: 0, top: 0, width: 960, height: 640 }) as DOMRect,
  });
  view.resize(960, 640, 1);
  /** Card textures there are now: not the room's, nor the signatures'. */
  const before = new Set(io.live);
  const cards = () => [...io.live].filter((t) => !before.has(t)).length;
  /** [ms] of frames. */
  const run = async (ms: number) => {
    for (let t = 0; t < ms; t += 16) {
      await vi.advanceTimersByTimeAsync(16);
      view.update(16);
      view.draw();
    }
  };
  /** What was asked for is loaded. */
  const settled = async () => {
    const all = kit.settled();
    await vi.runAllTimersAsync();
    await all;
  };
  return { kit, view, drawn, cards, run, settled };
}

const faces: Face[] = art.cards.map((c) => ({ card: c.id, signed: false }));
/** The cards either side of the [i]th of the album. */
const near = (i: number) => [faces[i - 1], faces[i + 1]].filter((f): f is Face => !!f);
const infoOf = (f: Face) => (f.signed ? art.signed(f.card) : art.card(f.card))!;

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetModules();
  io.made.clear();
  io.live.clear();
  io.late = null;
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a card looked at", () => {
  it("keeps the textures of the card on show and those beside it while the album is paged through", async () => {
    const { kit, view, cards, run, settled } = await setup(true);
    let most = 0;
    for (const [i, face] of faces.entries()) {
      if (i === 0) view.open(face, { near: near(i) });
      else view.change(face, 1, near(i));
      await run(100);
      await settled();
      most = Math.max(most, cards());
      expect(kit.faces(infoOf(face))).not.toBeNull();
    }
    // Fronts of three cards and their finishes, and their backs: never every card seen.
    expect(most).toBeLessThanOrEqual(12);
    view.dispose();
    expect(cards()).toBe(0);
  });

  it("lets go of what was paged past at the end of its way out, and draws every card it shows", async () => {
    const { kit, view, drawn, cards, run, settled } = await setup(false);
    view.open(faces[0], { near: near(0) });
    await run(1500);
    // Quickly on, each before the last has come in.
    for (let i = 1; i <= 6; i++) {
      view.change(faces[i], 1, near(i));
      await run(48);
    }
    await run(1500);
    await settled();
    expect(kit.faces(infoOf(faces[6]))).not.toBeNull();
    expect(cards()).toBeLessThanOrEqual(12);
    // Back to one let go of: the card before stays until it is there again.
    expect(kit.faces(infoOf(faces[1]))).toBeNull();
    for (let i = 5; i >= 1; i--) {
      view.change(faces[i], -1, near(i));
      await run(48);
    }
    await run(1500);
    expect(kit.faces(infoOf(faces[1]))).not.toBeNull();
    expect(drawn.length).toBeGreaterThan(100);
    expect(drawn.filter((d) => !d.faces)).toEqual([]);
    view.dispose();
  });

  it("lets go of a card paged past quickly whose textures came after the one paged to", async () => {
    const { kit, view, run, settled } = await setup(true);
    view.open(faces[0], { near: near(0) });
    await run(100);
    let come!: () => void;
    io.late = { url: infoOf(faces[1]).front[0], come: new Promise<void>((done) => { come = done; }) };
    for (let i = 1; i <= 5; i++) view.change(faces[i], 1, near(i));
    await run(100);
    expect(kit.faces(infoOf(faces[5]))).not.toBeNull();
    come();
    await settled();
    await run(100);
    const front = infoOf(faces[1]).front[0];
    expect(io.made.get(front)).toBe(1);
    expect([...io.live].some((t) => (t as { url: string }).url === front)).toBe(false);
    view.dispose();
  });

  it("turns between a card and its signed one on the same textures", async () => {
    const { view, drawn, run, settled } = await setup(false);
    const solo = faces[0], signed = { card: solo.card, signed: true };
    view.open(solo, { near: near(0) });
    await run(1500);
    await settled();
    const made = new Map(io.made);
    view.change(signed, 0, near(0));
    await run(1500);
    view.change(solo, 0, near(0));
    await run(1500);
    expect(io.made).toEqual(made);
    expect(drawn.filter((d) => !d.faces)).toEqual([]);
    view.dispose();
  });
});
