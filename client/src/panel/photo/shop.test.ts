import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref } from "vue";
import type { BoxPlace } from "../../photo/place";
import type { PhotocardBox } from "../../stores/photocards";
import type { ShelfStage } from "./shop";

interface Fake { box: PhotocardBox | null; opened: number }
const fake = {
  shelf: ref<string[]>([]),
  views: reactive<Record<string, Fake>>({}),
  buying: ref(""),
  error: ref(""),
  buy: vi.fn<(series: string) => Promise<PhotocardBox | null>>(),
  away: vi.fn<(series: string) => void>(),
};
vi.mock("../../photocards", () => ({ photoSeries: ["a", "b", "c", "z"].map((id) => ({ id })) }));
vi.mock("../../stores/photocards", () => ({
  photoBuying: fake.buying,
  photoError: fake.error,
  photoOn: computed(() => fake.shelf.value.length > 0),
  photoShelf: computed(() => fake.shelf.value.map((series) => ({ series }))),
  photoView: (series: string) => {
    const { box, opened } = fake.views[series] ?? { box: null, opened: 0 };
    return { series, box, opened, opening: !!box && opened < box.cards.length };
  },
  buyPhotoBox: (series: string) => fake.buy(series),
  putPhotoBoxAway: (series: string) => fake.away(series),
}));

const BOX: PhotocardBox = { id: 7, ts: 0, price: 10, cards: [{ item: "a" }, { item: "b" }] };
const PLACE = { cx: 1, cy: 2, css: 1 } as BoxPlace;

/** A shelf whose moves end when told. */
function stage() {
  const ends: (() => void)[] = [];
  const s = {
    pack: vi.fn(() => new Promise<void>((done) => { ends.push(done); })), unpack: vi.fn(),
    stow: vi.fn(() => new Promise<void>((done) => { ends.push(done); })), hand: vi.fn(() => PLACE), place: vi.fn(() => PLACE),
    back: vi.fn(),
  } satisfies ShelfStage;
  return { s, end: () => { for (const f of ends.splice(0)) f(); } };
}
const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

let stored: Record<string, string> = {};
async function shop() {
  vi.resetModules();
  return import("./shop");
}
beforeEach(() => {
  stored = {};
  vi.stubGlobal("localStorage", { getItem: (k: string) => stored[k] ?? null, setItem: (k: string, v: string) => { stored[k] = v; } });
  fake.shelf.value = ["a"];
  for (const k of Object.keys(fake.views)) delete fake.views[k];
  fake.buying.value = "";
  fake.error.value = "";
  fake.buy.mockReset();
  fake.away.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("the series on show", () => {
  it("is the first on the shelf, or the one with a box that waits, or the one picked", async () => {
    fake.shelf.value = ["a", "b", "c"];
    const m = await shop();
    expect(m.shopSeries.value).toBe("a");
    fake.views.b = { box: BOX, opened: 1 };
    expect(m.shopSeries.value).toBe("b");
    m.pickSeries("c");
    expect(m.shopSeries.value).toBe("c");
    delete fake.views.b;
    fake.shelf.value = ["a"];
    expect(m.shopSeries.value).toBe("a");
    fake.shelf.value = [];
    expect(m.shopSeries.value).toBe("");
  });
  it("is also one taken off the shelf whose box was not opened to the end", async () => {
    const m = await shop();
    fake.views.z = { box: BOX, opened: 1 };
    expect(m.shelfIds.value).toEqual(["a", "z"]);
    expect(m.shopSeries.value).toBe("z");
    // It stays until the box was put away: the table that shows what came lies over it.
    fake.views.z = { box: BOX, opened: 2 };
    expect(m.shopSeries.value).toBe("a");
    expect(m.shelfIds.value).toEqual(["a", "z"]);
    fake.views.z = { box: null, opened: 0 };
    expect(m.shelfIds.value).toEqual(["a"]);
  });
  it("stays while a box is bought or opened", async () => {
    fake.shelf.value = ["a", "b"];
    const m = await shop();
    m.packing.value = true;
    m.pickSeries("b");
    expect(m.shopSeries.value).toBe("a");
  });
});

describe("buying on the shelf", () => {
  it("packs while the request is out and hands the box over once both are done", async () => {
    const m = await shop(), { s, end } = stage();
    m.shelfStage.value = s;
    let answer!: (b: PhotocardBox) => void;
    fake.buy.mockReturnValue(new Promise((done) => { answer = done; }));
    const done = m.buyOnShelf();
    expect(m.packing.value).toBe(true);
    expect(s.pack).toHaveBeenCalledOnce();
    void m.buyOnShelf();
    expect(fake.buy).toHaveBeenCalledOnce();
    answer(BOX);
    await flush();
    expect(m.photoRun.value).toBeNull();
    end();
    await done;
    expect(m.photoRun.value).toEqual({ series: "a", box: BOX, start: "new" });
    expect(s.hand).not.toHaveBeenCalled();
    expect(m.packing.value).toBe(false);
    expect(m.photoBusy.value).toBe(true);
  });
  it("takes everything out again when it could not be bought", async () => {
    const m = await shop(), { s } = stage();
    m.shelfStage.value = s;
    fake.buy.mockResolvedValue(null);
    await m.buyOnShelf();
    expect(s.unpack).toHaveBeenCalledOnce();
    expect(m.photoRun.value).toBeNull();
    expect(m.photoBusy.value).toBe(false);
  });
  it("goes to the table without a shelf", async () => {
    const m = await shop();
    fake.buy.mockResolvedValue(BOX);
    await m.buyOnShelf();
    expect(m.photoRun.value).toEqual({ series: "a", box: BOX, start: "new" });
  });
  it("goes to the table although the shelf was taken away, or only came, meanwhile", async () => {
    const m = await shop(), { s } = stage();
    m.shelfStage.value = s;
    fake.buy.mockResolvedValue(BOX);
    const lost = m.buyOnShelf();
    await flush();
    expect(m.photoRun.value).toBeNull();
    m.shelfStage.value = null;
    await lost;
    expect(m.photoRun.value).toMatchObject({ box: BOX });
    m.clearTable();
    let answer!: (b: PhotocardBox) => void;
    fake.buy.mockReturnValue(new Promise((done) => { answer = done; }));
    const late = m.buyOnShelf();
    m.shelfStage.value = s;
    answer(BOX);
    await late;
    expect([m.photoRun.value?.box, m.packing.value]).toEqual([BOX, false]);
  });
  it("shows the series it was bought of from then on", async () => {
    fake.shelf.value = ["a", "b"];
    const m = await shop();
    fake.views.b = { box: BOX, opened: 0 };
    expect(m.shopSeries.value).toBe("b");
    await m.resumeOnShelf();
    fake.views.b = { box: BOX, opened: 2 };
    expect(m.shopSeries.value).toBe("b");
  });
});

describe("the page left on the way", () => {
  it.each([["packed", "answered"], ["answered", "packed"]])("leaves a bought box on the shelf: left before it was %s and %s", async (first) => {
    const m = await shop(), { s, end } = stage();
    m.shelfStage.value = s;
    let answer!: (b: PhotocardBox | null) => void;
    fake.buy.mockReturnValue(new Promise((done) => { answer = done; }));
    const done = m.buyOnShelf();
    if (first === "answered") { answer(BOX); await flush(); } else end();
    m.breakOff();
    m.shelfStage.value = null;
    expect([m.packing.value, m.photoBusy.value]).toEqual([false, false]);
    if (first === "answered") end(); else answer(BOX);
    await done;
    expect([m.photoRun.value, m.photoBusy.value, s.unpack.mock.calls.length]).toEqual([null, false, 0]);
    // The one after it goes its own way.
    const next = stage();
    m.shelfStage.value = next.s;
    fake.views.a = { box: BOX, opened: 0 };
    const on = m.resumeOnShelf();
    next.end();
    await on;
    expect(m.photoRun.value).toMatchObject({ start: "new" });
  });
  it("does not touch what is bought next when the first is refused late", async () => {
    const m = await shop(), one = stage(), two = stage();
    m.shelfStage.value = one.s;
    let refuse!: (b: null) => void;
    fake.buy.mockReturnValueOnce(new Promise((done) => { refuse = done; }));
    const first = m.buyOnShelf();
    m.breakOff();
    m.shelfStage.value = two.s;
    fake.views.a = { box: BOX, opened: 1 };
    const second = m.resumeOnShelf();
    refuse(null);
    await first;
    expect([m.packing.value, two.s.unpack.mock.calls.length]).toEqual([true, 0]);
    two.end();
    await second;
    expect(m.photoRun.value).toMatchObject({ start: "on" });
  });
  it("leaves nothing up once it is gone", async () => {
    const m = await shop();
    fake.buy.mockResolvedValue(BOX);
    await m.buyOnShelf();
    m.photoOver.value = { kind: "odds" };
    m.leaveShop();
    expect([m.photoRun.value, m.photoOver.value, m.photoBusy.value]).toEqual([null, null, false]);
  });
});

describe("a box that waits", () => {
  it("goes to the table as new while nothing of it is open, else to go on with", async () => {
    const m = await shop(), { s, end } = stage();
    m.shelfStage.value = s;
    fake.views.a = { box: BOX, opened: 0 };
    const first = m.resumeOnShelf();
    expect(m.photoBusy.value).toBe(true);
    end();
    await first;
    expect(m.photoRun.value).toMatchObject({ start: "new" });
    m.clearTable();
    expect(s.back).toHaveBeenCalledOnce();
    fake.views.a = { box: BOX, opened: 1 };
    const second = m.resumeOnShelf();
    end();
    await second;
    expect(m.photoRun.value).toMatchObject({ start: "on" });
  });
  it("does nothing once all of it is open", async () => {
    const m = await shop();
    fake.views.a = { box: BOX, opened: 2 };
    await m.resumeOnShelf();
    expect(m.photoRun.value).toBeNull();
  });
});

describe("the table", () => {
  it("gets another box without one coming from the shelf", async () => {
    const m = await shop();
    fake.buy.mockResolvedValue(BOX);
    await m.buyOnShelf();
    const next = { ...BOX, id: 8 };
    fake.buy.mockResolvedValue(next);
    expect(await m.buyAnother()).toEqual(next);
    expect(m.photoRun.value).toEqual({ series: "a", box: next, start: "again" });
    fake.buy.mockResolvedValue(null);
    expect(await m.buyAnother()).toBeNull();
    expect(m.photoRun.value?.box.id).toBe(8);
  });
  it("puts the box away when it is cleared", async () => {
    const m = await shop();
    fake.buy.mockResolvedValue(BOX);
    await m.buyOnShelf();
    m.clearTable();
    expect(fake.away).toHaveBeenCalledWith("a");
    expect(m.photoBusy.value).toBe(false);
    m.clearTable();
    expect(fake.away).toHaveBeenCalledOnce();
  });
});

describe("the key visual the page opens on", () => {
  it("is up the first time a series is come to", async () => {
    const m = await shop();
    m.openPage("a");
    expect(m.poster.value).toBe("opening");
    m.opened.add("a");
    m.breakOff();
    expect(m.poster.value).toBe("");
    m.openPage("a");
    expect(m.poster.value).toBe("");
    m.openPage("b");
    expect(m.poster.value).toBe("opening");
  });

  it("stays away under a dialog, while a box is bought, and where it is asked for", async () => {
    const m = await shop();
    m.photoOver.value = { kind: "odds" };
    m.openPage("a");
    expect(m.poster.value).toBe("");
    m.photoOver.value = null;
    m.packing.value = true;
    m.openPage("a");
    expect(m.poster.value).toBe("");
    m.packing.value = false;
    vi.stubGlobal("document", { querySelector: () => ({}) });
    m.openPage("a");
    expect(m.poster.value).toBe("");
    vi.stubGlobal("document", { querySelector: () => null });
    m.poster.value = "look";
    m.openPage("a");
    expect(m.poster.value).toBe("look");
  });
});

describe("the mark of something new", () => {
  it("shows until the page was looked at, and again for another series", async () => {
    const m = await shop();
    expect(m.shopFresh.value).toBe(true);
    m.markShopSeen();
    expect(m.shopFresh.value).toBe(false);
    fake.shelf.value = ["a", "b"];
    expect(m.shopFresh.value).toBe(true);
    m.markShopSeen();
    expect((await shop()).shopFresh.value).toBe(false);
  });
  it("does not show without photocards, nor where storage is closed", async () => {
    fake.shelf.value = [];
    expect((await shop()).shopFresh.value).toBe(false);
    fake.shelf.value = ["a"];
    vi.stubGlobal("localStorage", { getItem() { throw new Error("closed"); }, setItem() { throw new Error("closed"); } });
    const m = await shop();
    m.markShopSeen();
    expect(m.shopFresh.value).toBe(false);
  });
});
