import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, type Ref } from "vue";
import { exampleEconomy } from "../test/economy";
import type { PhotocardConfig } from "./economy";
import type { PhotocardBox, PhotocardPull, PhotocardSave, PhotocardState } from "./photocards";

const parkTry = vi.fn();
vi.mock("./park", () => ({ parkTry: (...a: unknown[]) => parkTry(...a) }));
/** The save's status, fresh for each test (doMock): module copies of earlier tests keep watching their own. */
const player = { status: null as unknown as Ref<{ player: string } | null>, loadEconomy: vi.fn() };

/** A second series of this build: the cards of the first under an id of its own. */
const { B } = vi.hoisted(() => ({ B: "later" }));
vi.mock("../manifest", async (original) => {
  const m = await original<typeof import("../manifest")>();
  const first = m.manifest.photocards[0]!;
  return { ...m, manifest: { ...m.manifest, photocards: [first, { ...first, id: B, name: "以后", event: "以后" }] } };
});

type Reply = { ok: true; data: unknown } | { ok: false; error: { status: number; code: string; message: string; detail: object } };
interface Call { method: string; path: string; body: Record<string, unknown> | undefined; answer: (r: Reply) => void }

const CFG = exampleEconomy.photocards![0]!;
const A = CFG.series;
const CFG2: PhotocardConfig = {
  ...CFG, series: B, price: CFG.price + 100, daily: CFG.daily + 1, signPity: CFG.signPity + 2, swap: CFG.swap + 1,
};
/** Both are on the shelf. */
const ECONOMY = { ...exampleEconomy, photocards: [CFG, CFG2] };
const S = (card: string, series = A) => `photo:${series}/${card}`;
const SIGN = (card: string, series = A) => `sign:${series}/${card}`;
const SOLOS = ["diana", "bella", "eileen"].flatMap((m) => [1, 2, 3, 4].map((n) => `${m}-${n}`));
const SIGNS = (series = A) => SOLOS.map((card) => SIGN(card, series));
const NOW = Date.UTC(2026, 11, 1, 4); // noon in China

let calls: Call[] = [];
let stored: Record<string, string> = {};
const ok = (data: unknown): Reply => ({ ok: true, data });
const fail = (status: number, code: string, message = code): Reply => ({ ok: false, error: { status, code, message, detail: {} } });
const flush = () => vi.advanceTimersByTimeAsync(0);
const paths = () => calls.map((c) => c.path.replace("/api/photocards", ""));

const pulls = (series = A): PhotocardPull[] => [
  { item: S("diana-1", series), new: true }, { item: S("diana-1", series), shards: 10 },
  { item: SIGN("bella-2", series), new: true }, { item: SIGN("bella-2", series), spare: true },
  { item: S("bella-1", series), new: true },
];
const box = (id: number, series = A, over: Partial<PhotocardBox> = {}): PhotocardBox =>
  ({ id, ts: NOW / 1000, price: CFG.price, cards: pulls(series), ...over });
type Save = Partial<PhotocardSave>;
const save = (cfg: PhotocardConfig, over: Save = {}): PhotocardSave =>
  ({ owned: [], left: cfg.daily, boxes: 0, dry: 0, spare: 0, box: null, ...over });
const state = (a: Save = {}, b: Save = {}): PhotocardState =>
  ({ day: "2026-12-01", series: { [A]: save(CFG, a), [B]: save(CFG2, b) } });
const answer = (a: Save = {}, b: Save = {}, extra: object = {}) => ok({ photocards: state(a, b), ...extra });
/** A series after buying its box [id]. */
const bought = (id: number, series = A, over: Save = {}): Save => ({
  owned: [S("diana-1", series), S("bella-1", series), SIGN("bella-2", series)], left: 2, boxes: 1, dry: 0, spare: 1,
  box: box(id, series), ...over,
});
/** A series once that box is opened. */
const opened = (series = A, over: Save = {}) => bought(0, series, { box: null, ...over });

type Store = typeof import("./photocards");
/** The store, loaded with what the server tells of either series; what it asks after that is left in calls. */
async function store(a: Save | null = {}, b: Save = {}): Promise<Store> {
  const P = await import("./photocards");
  if (a) {
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer(a, b));
    expect(await pending).toBe(true);
    calls.shift();
  }
  return P;
}
/** A store with box 1 of the first series bought and nothing opened. */
async function withBox(over: Save = {}): Promise<Store> {
  const P = await store();
  const pending = P.buyPhotoBox(A);
  calls[0]!.answer(answer(bought(1, A, over)));
  expect((await pending)!.id).toBe(1);
  calls = [];
  return P;
}
/** The store as the next start has it, loaded with the same storage. */
async function restart(a: Save, b: Save = {}): Promise<Store> {
  vi.resetModules();
  calls = [];
  (await import("./economy")).setEconomy(ECONOMY);
  return store(a, b);
}
/** Another shelf comes with the economy. */
async function shelve(...photocards: PhotocardConfig[]): Promise<void> {
  (await import("./economy")).setEconomy({ ...ECONOMY, photocards });
  await nextTick();
}
/** What the pages show of the save's cards. */
const shown = (P: Store, series = A) => ({ owned: P.photoView(series).owned, spare: P.photoView(series).spare });
const table = (P: Store, series = A) => [P.photoView(series).box?.id, P.photoView(series).opened];
/** [n] bags of the box on the table are open. */
const tear = (P: Store, series: string, n: number) => P.openPhotoBags(series, P.photoView(series).box?.id ?? 0, n);

beforeEach(async () => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  vi.resetModules();
  player.status = ref({ player: "A" });
  player.loadEconomy.mockReset();
  vi.doMock("./player", () => ({ status: player.status, loadEconomy: player.loadEconomy }));
  stored = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => stored[k] ?? null,
    setItem: (k: string, v: string) => { stored[k] = v; },
    removeItem: (k: string) => { delete stored[k]; },
  });
  (await import("./economy")).setEconomy(ECONOMY);
  calls = [];
  parkTry.mockReset();
  parkTry.mockImplementation((method: string, path: string, body?: Record<string, unknown>) =>
    new Promise<Reply>((resolve) => calls.push({ method, path, body, answer: resolve })));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("loading", () => {
  it("shows the shelf at once and the save once the server answered", async () => {
    const P = await store(null);
    expect(P.photoView(A)).toEqual({
      series: A, cfg: CFG, save: null, box: null, opened: 0, opening: false, owned: new Set(), spare: 0,
      signsWhole: false, pity: null, canSwap: false,
    });
    expect([P.photoOn.value, P.photoAlbums.value, P.photoLeft(A)]).toEqual([true, [A, B], null]);
    await store({ owned: [S("diana-1")], left: 2, dry: 3, spare: 1 }, { left: 1 });
    expect(P.photoState.value!.series[A]).toMatchObject({ left: 2, dry: 3, spare: 1 });
    expect(P.photoView(A)).toEqual({
      series: A, cfg: CFG, save: P.photoState.value!.series[A], box: null, opened: 0, opening: false,
      owned: new Set([S("diana-1")]), spare: 1, signsWhole: false, pity: CFG.signPity - 3, canSwap: false,
    });
    expect(P.photoView(B)).toMatchObject({ series: B, cfg: CFG2, spare: 0, pity: CFG2.signPity });
    expect([P.photoLeft(A), P.photoLeft(B)]).toEqual([2, 1]);
  });

  it("says why it failed and keeps what it had", async () => {
    const P = await store({ left: 2 });
    const pending = P.loadPhotocards();
    calls[0]!.answer(fail(0, "offline"));
    expect(await pending).toBe(false);
    expect(P.photoError.value).toBe("无法连接服务器");
    expect(P.photoState.value!.series[A]!.left).toBe(2);
  });

  it.each([["no", undefined], ["an empty", []], ["a nonsensical", CFG as never]])(
    "asks nothing of a server with %s shelf, and loads once it has photocards", async (_name, photocards) => {
      const { setEconomy } = await import("./economy");
      setEconomy({ ...ECONOMY, photocards });
      const P = await store(null);
      expect([P.photoOn.value, P.photoShelf.value, P.photoAlbums.value]).toEqual([false, [], []]);
      expect(await P.loadPhotocards()).toBe(false);
      expect(calls).toEqual([]);
      await shelve(CFG);
      expect([P.photoOn.value, P.photoShelf.value]).toEqual([true, [CFG]]);
      expect(paths()).toEqual([""]);
    });

  it.each([["no_photocards"], ["http_error"]])(
    "turns off when the server answers 404 %s, until its economy comes again", async (code) => {
      const P = await store(null);
      const pending = P.loadPhotocards();
      calls[0]!.answer(fail(404, code));
      expect(await pending).toBe(false);
      expect([P.photoOn.value, P.photoAlbums.value]).toEqual([false, []]);
      await shelve(CFG, CFG2);
      expect([P.photoOn.value, P.photoAlbums.value]).toEqual([true, [A, B]]);
      // Asked again, as nothing was loaded yet.
      expect(paths()).toEqual(["", ""]);
    });

  it("is on again when the server answers after all", async () => {
    const P = await store(null);
    const none = P.loadPhotocards();
    const some = P.loadPhotocards();
    calls[0]!.answer(fail(404, "no_photocards"));
    await none;
    calls[1]!.answer(answer());
    expect([await some, P.photoOn.value]).toEqual([true, true]);
  });

  it.each([["no_series"], ["no_box"], ["no_save"]])("stays on when the server answers 404 %s", async (code) => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(fail(404, code));
    expect(await pending).toBeNull();
    expect(P.photoOn.value).toBe(true);
  });

  it("never puts an older answer over a newer one", async () => {
    const P = await store();
    const first = P.loadPhotocards();
    const second = P.loadPhotocards();
    calls[1]!.answer(answer({ left: 1 }));
    await second;
    calls[0]!.answer(answer({ left: 3 }));
    await first;
    expect(P.photoState.value!.series[A]!.left).toBe(1);
  });

  it("takes an answer without photocards for a failure", async () => {
    const P = await store({ left: 2 });
    for (const data of [null, {}, { photocards: {} }]) {
      const pending = P.loadPhotocards();
      calls.pop()!.answer(ok(data));
      expect(await pending).toBe(false);
      expect([P.photoState.value!.series[A]!.left, P.photoError.value]).toEqual([2, "无法连接服务器"]);
    }
  });

  it("loads again when the shelf changes, and not when it comes as it was", async () => {
    const P = await store();
    await shelve(CFG, CFG2);
    expect(calls).toEqual([]);
    const shelves = [[CFG2], [CFG2, CFG], [CFG2, { ...CFG, daily: 0 }], [{ ...CFG, daily: CFG2.daily }, { ...CFG2, daily: 0 }]];
    for (const shelf of shelves) {
      calls = [];
      await shelve(...shelf);
      expect(paths()).toEqual([""]);
      calls[0]!.answer(answer());
      await flush();
    }
    // Nothing to ask without any.
    calls = [];
    await shelve();
    expect([calls.length, P.photoOn.value]).toEqual([0, false]);
  });
});

describe("the shelf and the albums", () => {
  it("leave out a series this build lacks, in the economy and in answers", async () => {
    await shelve({ ...CFG, series: "unknown" }, CFG2, CFG);
    const P = await store(null);
    expect(P.photoShelf.value).toEqual([CFG2, CFG]);
    const pending = P.loadPhotocards();
    const unknown = save(CFG, bought(9));
    calls[0]!.answer(ok({ photocards: { day: "2026-12-01", series: { unknown, ...state({ left: 1 }).series } } }));
    expect(await pending).toBe(true);
    const nothing = {
      series: "unknown", cfg: null, save: null, box: null, opened: 0, opening: false, owned: new Set(), spare: 0,
      signsWhole: false, pity: null, canSwap: false,
    };
    expect([P.photoView("unknown"), P.photoView("")]).toEqual([nothing, { ...nothing, series: "" }]);
    expect([P.photoLeft("unknown"), await P.buyPhotoBox("unknown")]).toEqual([null, null]);
    expect(await P.swapPhoto("sign:unknown/diana-1")).toBeNull();
    P.openPhotoBags("unknown", 1, 5);
    P.putPhotoBoxAway("unknown");
    expect([calls.length, P.photoError.value, P.photoAlbums.value]).toEqual([1, "", [B, A]]);
    expect(P.photoLeft(A)).toBe(1);
  });

  it("do without a series the server lacks", async () => {
    const P = await withBox();
    const pending = P.loadPhotocards();
    calls[0]!.answer(ok({ photocards: { day: "2026-12-01", series: { [B]: save(CFG2) } } }));
    expect(await pending).toBe(true);
    expect(P.photoView(A)).toMatchObject({ cfg: CFG, save: null, box: null, pity: null });
    expect([P.photoLeft(A), P.photoView(B).pity]).toEqual([null, CFG2.signPity]);
  });

  it("show the albums of the shelf in its order, then those of other series the save has a card of", async () => {
    await shelve(CFG2);
    const P = await store();
    expect([P.photoShelf.value, P.photoAlbums.value]).toEqual([[CFG2], [B]]);
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer({ owned: [S("diana-1")], left: 0 }, { owned: [S("diana-1", B)] }));
    await pending;
    expect(P.photoAlbums.value).toEqual([B, A]);
    // With nothing of this build on the shelf, the albums are all there is.
    await shelve({ ...CFG, series: "unknown" });
    expect([P.photoOn.value, P.photoShelf.value, P.photoAlbums.value]).toEqual([false, [], [A, B]]);
    // The server has none any more.
    await shelve();
    expect(P.photoAlbums.value).toEqual([]);
  });

  it("show no album for what bags left to open hold", async () => {
    await shelve(CFG2);
    const P = await store(bought(1));
    expect(P.photoAlbums.value).toEqual([B]);
    tear(P, A, 1);
    expect(P.photoAlbums.value).toEqual([B, A]);
  });

  it("keep what a save has of a series off the shelf, and let its box be opened", async () => {
    await shelve(CFG2);
    const owned = [...SIGNS().slice(2), ...bought(1).owned!];
    const P = await store(bought(1, A, { owned, left: 0, spare: CFG.swap + 1 }));
    expect(P.photoView(A)).toMatchObject({ cfg: null, opened: 0, opening: true, spare: CFG.swap, pity: null });
    expect([P.photoLeft(A), P.photoLeft(A, NOW + 86400_000)]).toEqual([0, 0]);
    expect((await P.buyPhotoBox(A))!.id).toBe(1);
    tear(P, A, 5);
    expect(calls.map((c) => c.body)).toEqual([{ box: 1 }]);
    calls[0]!.answer(answer(opened(A, { owned, left: 0, spare: CFG.swap + 1 })));
    await flush();
    P.putPhotoBoxAway(A);
    expect(P.photoView(A)).toMatchObject({ cfg: null, box: null, spare: CFG.swap + 1, pity: null, canSwap: false });
    expect(await P.swapPhoto(SIGN("diana-1"))).toBeNull();
    expect(calls).toHaveLength(1);
  });
});

describe("photoView", () => {
  it("is followed by what reads it, and stays the same object until something changes", async () => {
    const P = await store();
    const a = computed(() => P.photoView(A));
    const b = computed(() => P.photoView(B).opened);
    expect([a.value.opened, b.value]).toEqual([0, 0]);
    expect(a.value).toBe(P.photoView(A));
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(answer(bought(1), bought(2, B)));
    await pending;
    expect([a.value.opening, a.value.box!.id, b.value]).toEqual([true, 1, 0]);
    const before = [P.photoView(A), P.photoView(B)];
    tear(P, A, 2);
    expect([a.value.opened, b.value]).toEqual([2, 0]);
    expect([P.photoView(A) === before[0], P.photoView(B) === before[1]]).toEqual([false, true]);
    tear(P, B, 1);
    expect([a.value.opened, b.value]).toEqual([2, 1]);
    P.resetPhotocards();
    expect([a.value.box, a.value.save, b.value]).toEqual([null, null, 0]);
    await shelve(CFG2);
    expect(a.value.cfg).toBeNull();
  });
});

describe("buying and opening a box", () => {
  it("puts the box on the table and shows its bags one by one", async () => {
    const P = await withBox();
    expect(P.photoView(A)).toMatchObject({ opened: 0, opening: true, pity: null });
    expect(P.photoView(A).box!.cards).toHaveLength(5);
    expect(shown(P)).toEqual({ owned: new Set(), spare: 0 });
    tear(P, A, 1);
    expect(shown(P)).toEqual({ owned: new Set([S("diana-1")]), spare: 0 });
    tear(P, A, 3);
    expect(shown(P).owned).toEqual(new Set([S("diana-1"), SIGN("bella-2")]));
    tear(P, A, 4);
    expect(shown(P).spare).toBe(1);
    // Never fewer than before.
    tear(P, A, 2);
    expect(table(P)).toEqual([1, 4]);
    expect(calls).toEqual([]);

    tear(P, A, 99);
    expect(P.photoView(A)).toMatchObject({ opened: 5, opening: false });
    expect(calls.map((c) => [c.method, c.path, c.body])).toEqual([["POST", "/api/photocards/open", { box: 1 }]]);
    calls[0]!.answer(answer(opened()));
    await flush();
    // The box stays for a look at what came, until it is put away.
    expect(table(P)).toEqual([1, 5]);
    expect(P.photoView(A).pity).toBe(CFG.signPity);
    P.putPhotoBoxAway(A);
    expect(table(P)).toEqual([undefined, 0]);
    expect(shown(P).owned.size).toBe(3);
  });

  it("does not put away a box with bags left", async () => {
    const P = await withBox();
    P.putPhotoBoxAway(A);
    expect(table(P)).toEqual([1, 0]);
  });

  it("buys nothing while one is open on the table, or on its way", async () => {
    const P = await withBox();
    expect((await P.buyPhotoBox(A))!.id).toBe(1);
    expect(calls).toEqual([]);
    tear(P, A, 5);
    calls[0]!.answer(answer(opened()));
    await flush();
    calls = [];
    const first = P.buyPhotoBox(A);
    expect(P.photoBuying.value).toBe(A);
    expect(await P.buyPhotoBox(A)).toBeNull();
    expect(calls.map((c) => [c.method, c.path, c.body])).toEqual([["POST", "/api/photocards/buy", { series: A, price: CFG.price }]]);
    calls[0]!.answer(answer(bought(2, A, { left: 1, boxes: 2 })));
    expect(await first).toBe(P.photoView(A).box);
    expect([P.photoBuying.value, ...table(P)]).toEqual(["", 2, 0]);
  });

  it.each([["photo_sold_out", "今天买完了"], ["photo_off_sale", "没有在售"], ["no_shards", "碎片不足"]])(
    "says why it was refused: %s", async (code, words) => {
      const P = await store();
      const pending = P.buyPhotoBox(A);
      calls[0]!.answer(fail(409, code, words));
      expect(await pending).toBeNull();
      expect([P.photoError.value, P.photoBuying.value, P.photoView(A).box]).toEqual([words, "", null]);
      // What it is about may be news here: the state comes anew, and the words stay.
      expect(paths()).toEqual(["/buy", ""]);
      calls[1]!.answer(answer({ left: 0 }));
      await flush();
      expect([P.photoLeft(A), P.photoError.value, player.loadEconomy.mock.calls.length]).toEqual([0, words, 0]);
    });

  it("asks for the prices anew when the server's is another by now", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    expect(calls[0]!.body).toEqual({ series: A, price: CFG.price });
    calls[0]!.answer(fail(409, "price_changed", "价格已更新"));
    expect(await pending).toBeNull();
    expect([P.photoError.value, player.loadEconomy.mock.calls.length]).toEqual(["价格已更新", 1]);
    await shelve({ ...CFG, price: CFG.price + 5 }, CFG2);
    void P.buyPhotoBox(A);
    expect(calls.at(-1)!.body).toEqual({ series: A, price: CFG.price + 5 });
  });

  it("leaves it to the server whether a series off the shelf is sold", async () => {
    await shelve(CFG2);
    const P = await store();
    const pending = P.buyPhotoBox(A);
    expect(calls[0]).toMatchObject({ path: "/api/photocards/buy", body: { series: A, price: undefined } });
    calls[0]!.answer(answer(bought(1)));
    expect((await pending)!.id).toBe(1);
  });

  it("says nothing of the last failure while it tries again", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(fail(409, "no_shards"));
    await pending;
    void P.buyPhotoBox(B);
    expect(P.photoError.value).toBe("");
  });

  it.each([["no answer", 0, "offline"], ["a lost relay", 0, "desktop"], ["a proxy's error", 502, "http_error"]])(
    "finds the box that was bought although the answer was lost: %s", async (_name, status, code) => {
      const P = await store();
      const pending = P.buyPhotoBox(B);
      calls[0]!.answer(fail(status, code));
      await flush();
      expect(paths()).toEqual(["/buy", ""]);
      calls[1]!.answer(answer({}, bought(4, B)));
      expect((await pending)!.id).toBe(4);
      expect([...table(P, B), P.photoError.value]).toEqual([4, 0, ""]);
    });

  it("says it has no connection when the box was not bought", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(fail(0, "offline"));
    await flush();
    // The box of another series is not the one that was bought.
    calls[1]!.answer(answer({}, bought(7, B)));
    expect(await pending).toBeNull();
    expect(P.photoError.value).toBe("无法连接服务器");
  });

  it("holds back what a box that completes the signed cards paid until it is opened", async () => {
    const last = SIGN("eileen-4");
    const cards: PhotocardPull[] = [{ item: last, new: true }, { item: SIGN("diana-1"), shards: 200 }];
    const settled = { cards: 3, shards: 600 };
    const P = await withBox({ owned: SIGNS(), spare: 0, box: box(1, A, { cards, settled }) });
    expect(shown(P).spare).toBe(3);
    expect([shown(P).owned.has(last), P.photoView(A).signsWhole]).toEqual([false, false]);
    tear(P, A, 2);
    expect(P.photoView(A)).toMatchObject({ spare: 0, signsWhole: true, pity: null });
  });

  it("shows none put by where the bags left to open hold more than there are", async () => {
    const P = await withBox({ spare: 0 });
    expect(shown(P).spare).toBe(0);
  });

  it("promises a signed card with the next box at the latest", async () => {
    const P = await store({ dry: CFG.signPity - 1 }, { dry: CFG2.signPity + 3 });
    expect([P.photoView(A).pity, P.photoView(B).pity]).toEqual([1, 1]);
  });

  it("loads first what is not known yet", async () => {
    const P = await store(null);
    const pending = P.buyPhotoBox(A);
    expect([paths(), P.photoBuying.value]).toEqual([[""], A]);
    calls[0]!.answer(answer());
    await flush();
    expect(paths()).toEqual(["", "/buy"]);
    calls[1]!.answer(answer(bought(1)));
    expect((await pending)!.id).toBe(1);
    P.resetPhotocards();
    calls = [];
    const none = P.buyPhotoBox(A);
    calls[0]!.answer(fail(0, "offline"));
    expect(await none).toBeNull();
    expect([paths(), P.photoError.value, P.photoBuying.value]).toEqual([[""], "无法连接服务器", ""]);
  });
});

describe("the receipt of a box bought", () => {
  const receipt = (id: number, series = A) => ({ receipt: { series, box: box(id, series) } });

  it("puts the box on the table though a load sent later came back first, before the box", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    const load = P.loadPhotocards();
    expect(paths()).toEqual(["/buy", ""]);
    calls[1]!.answer(answer());
    await load;
    calls[0]!.answer(answer(bought(1), {}, receipt(1)));
    await flush();
    // That answer is older than the one taken: what the save has now is asked for once more.
    expect(paths()).toEqual(["/buy", "", ""]);
    calls[2]!.answer(answer(bought(1)));
    expect((await pending)!.id).toBe(1);
    expect([...table(P), P.photoView(A).opening, P.photoError.value]).toEqual([1, 0, true, ""]);
  });

  it("needs no other load when the state has the box", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(answer(bought(1), {}, receipt(1)));
    expect(await pending).toBe(P.photoView(A).box);
    expect(paths()).toEqual(["/buy"]);
  });

  it("says the box was opened on another device when the server has it opened by now", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(answer(opened(), {}, receipt(1)));
    await flush();
    expect(paths()).toEqual(["/buy", ""]);
    calls[1]!.answer(answer(opened()));
    expect(await pending).toBeNull();
    expect([...table(P), P.photoView(A).opening, P.photoError.value]).toEqual([undefined, 0, false, "这盒已在其他设备开完"]);
    expect(shown(P).owned.size).toBe(3);
  });

  it("opens the box of the receipt when the state cannot be loaded again", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    const load = P.loadPhotocards();
    calls[1]!.answer(answer());
    await load;
    calls[0]!.answer(answer(bought(1), {}, receipt(1)));
    await flush();
    calls[2]!.answer(fail(0, "offline"));
    expect((await pending)!.id).toBe(1);
    expect([...table(P), P.photoView(A).opening]).toEqual([1, 0, true]);
  });

  it("is looked for once more from a server that sends none", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    const load = P.loadPhotocards();
    calls[1]!.answer(answer());
    await load;
    calls[0]!.answer(answer(bought(1)));
    await flush();
    expect(paths()).toEqual(["/buy", "", ""]);
    calls[2]!.answer(answer(bought(1)));
    expect((await pending)!.id).toBe(1);
    expect(P.photoError.value).toBe("");
  });
});

describe("two series at once", () => {
  it("have a box on the table each", async () => {
    const P = await withBox();
    tear(P, A, 2);
    const pending = P.buyPhotoBox(B);
    expect([P.photoBuying.value, calls[0]!.path, calls[0]!.body]).toEqual([B, "/api/photocards/buy", { series: B, price: CFG2.price }]);
    calls[0]!.answer(answer(bought(1), bought(2, B)));
    expect((await pending)!.id).toBe(2);
    expect([table(P), table(P, B)]).toEqual([[1, 2], [2, 0]]);
    tear(P, B, 1);
    expect([table(P), table(P, B)]).toEqual([[1, 2], [2, 1]]);
    expect([shown(P).owned, shown(P, B).owned]).toEqual([new Set([S("diana-1")]), new Set([S("diana-1", B)])]);
    tear(P, B, 5);
    expect(calls[1]!.body).toEqual({ box: 2 });
    calls[1]!.answer(answer(bought(1), opened(B)));
    await flush();
    P.putPhotoBoxAway(A);
    P.putPhotoBoxAway(B);
    expect([table(P), table(P, B)]).toEqual([[1, 2], [undefined, 0]]);
    expect([P.photoView(A).pity, P.photoView(B).pity]).toEqual([null, CFG2.signPity]);
    // The one half open waits for no one: it comes back without a request, and the other is bought again.
    calls = [];
    const again = P.buyPhotoBox(B);
    expect((await P.buyPhotoBox(A))!.id).toBe(1);
    expect(paths()).toEqual(["/buy"]);
    calls[0]!.answer(answer(bought(1), bought(3, B)));
    expect((await again)!.id).toBe(3);
    expect([table(P), table(P, B)]).toEqual([[1, 2], [3, 0]]);
  });

  it("are bought one at a time", async () => {
    const P = await store();
    const first = P.buyPhotoBox(A);
    expect([await P.buyPhotoBox(B), P.photoBuying.value, calls.length]).toEqual([null, A, 1]);
    calls[0]!.answer(answer(bought(1)));
    expect((await first)!.id).toBe(1);
  });

  it("have their ends told at once, each until the server has heard it", async () => {
    const P = await store(bought(1), bought(2, B));
    tear(P, A, 5);
    tear(P, B, 5);
    expect(calls.map((c) => c.body)).toEqual([{ box: 1 }, { box: 2 }]);
    calls[0]!.answer(fail(0, "offline"));
    await flush();
    // Box 1 is still unopened to the server: it is told after the wait, not because of this answer.
    calls[1]!.answer(answer(bought(1), opened(B)));
    await flush();
    expect(calls).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls.map((c) => c.body)).toEqual([{ box: 1 }, { box: 2 }, { box: 1 }]);
    calls[2]!.answer(answer(opened(), opened(B)));
    await vi.advanceTimersByTimeAsync(60000);
    expect(calls).toHaveLength(3);
    expect([P.photoState.value!.series[A]!.box, P.photoState.value!.series[B]!.box]).toEqual([null, null]);
    expect([table(P), table(P, B)]).toEqual([[1, 5], [2, 5]]);
  });

  it("are bought without waiting for the end of the other's box", async () => {
    const P = await withBox();
    tear(P, A, 5);
    const other = P.buyPhotoBox(B);
    expect(paths()).toEqual(["/open", "/buy"]);
    calls[1]!.answer(answer(bought(1), bought(2, B)));
    expect((await other)!.id).toBe(2);
    expect([table(P), table(P, B), calls.length]).toEqual([[1, 5], [2, 0], 2]);
    // Its own has to be told first.
    const own = P.buyPhotoBox(A);
    await flush();
    expect(calls).toHaveLength(2);
    calls[0]!.answer(answer(opened(), bought(2, B)));
    await flush();
    expect(paths()).toEqual(["/open", "/buy", "/buy"]);
    calls[2]!.answer(answer(bought(3), bought(2, B)));
    expect((await own)!.id).toBe(3);
  });

  it("are over one by one when a box was opened on another device", async () => {
    const P = await store(bought(1), bought(2, B));
    tear(P, A, 2);
    tear(P, B, 3);
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer(opened(), bought(2, B)));
    await pending;
    expect([table(P), table(P, B)]).toEqual([[undefined, 0], [2, 3]]);
  });

  it("trade and count on their own", async () => {
    const solo = box(2, B, { cards: [{ item: S("diana-1", B), new: true }] });
    const P = await store({ spare: CFG.swap, dry: 2 }, bought(2, B, { owned: SIGNS(B), spare: 9, box: solo }));
    // The signed cards of one, and the bags left of its box, are nothing to the other.
    expect(P.photoView(B)).toMatchObject({ opening: true, signsWhole: true, canSwap: false, pity: null });
    expect(P.photoView(A)).toMatchObject({ opening: false, signsWhole: false, canSwap: true, pity: CFG.signPity - 2 });
    // Neither are its repeats: the second takes one more.
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer({ spare: CFG.swap }, { spare: CFG.swap }));
    await pending;
    expect([P.photoView(A).canSwap, P.photoView(B).canSwap]).toEqual([true, false]);
  });
});

describe("an opening broken off", () => {
  it("goes on where it was, each box on its own", async () => {
    const P = await store(bought(1), bought(2, B));
    tear(P, A, 2);
    tear(P, B, 4);
    tear(P, A, 3);
    const again = await restart(bought(1), bought(2, B));
    expect([table(again), table(again, B)]).toEqual([[1, 3], [2, 4]]);
    expect(shown(again).owned).toEqual(new Set([S("diana-1"), SIGN("bella-2")]));
    expect(shown(again, B)).toEqual({ owned: new Set([S("diana-1", B), SIGN("bella-2", B)]), spare: 1 });
  });

  it("goes on where it was after many boxes of another series", async () => {
    const P = await store(bought(1));
    tear(P, A, 2);
    for (let id = 10; id < 40; id++) {
      calls = [];
      const pending = P.buyPhotoBox(B);
      calls[0]!.answer(answer(bought(1), bought(id, B)));
      await pending;
      tear(P, B, 1);
      tear(P, B, 5);
      calls[1]!.answer(answer(bought(1), opened(B)));
      await flush();
      P.putPhotoBoxAway(B);
    }
    expect(table(await restart(bought(1), opened(B)))).toEqual([1, 2]);
  });

  it("goes on in this window without storage, whatever is loaded meanwhile", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("no storage"); },
      setItem: () => { throw new Error("no storage"); },
    });
    const P = await withBox();
    tear(P, A, 2);
    const before = P.photoView(A).box;
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer(bought(1)));
    await pending;
    expect(table(P)).toEqual([1, 2]);
    expect(P.photoView(A).box).toBe(before);
  });

  it("keeps the bags of one save's box apart from another's", async () => {
    const P = await withBox();
    tear(P, A, 2);
    player.status.value = { player: "B" };
    await flush();
    calls[0]!.answer(answer(bought(1)));
    await flush();
    expect(table(P)).toEqual([1, 0]);
  });

  it("tells the end again when the first time was lost, without showing the box anew", async () => {
    const P = await withBox();
    tear(P, A, 5);
    calls[0]!.answer(fail(0, "offline"));
    await flush();
    expect(calls).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toHaveLength(2);
    expect(calls[1]).toMatchObject({ path: "/api/photocards/open", body: { box: 1 } });
    calls[1]!.answer(answer(opened()));
    await flush();
    expect(P.photoState.value!.series[A]!.box).toBeNull();
    expect(table(P)).toEqual([1, 5]);
  });

  it("does not tell the end again when the server refused it", async () => {
    const P = await withBox();
    tear(P, A, 5);
    calls[0]!.answer(fail(403, "refused"));
    await vi.advanceTimersByTimeAsync(60000);
    expect(calls).toHaveLength(1);
    const pending = P.buyPhotoBox(A);
    calls[1]!.answer(fail(403, "refused"));
    expect(await pending).toBeNull();
    expect([paths(), P.photoError.value]).toEqual([["/open", "/open"], "无法连接服务器"]);
  });

  it("tells the ends on the next start, and puts no box on the table for them", async () => {
    const P = await store(bought(1), bought(2, B));
    tear(P, A, 5);
    tear(P, B, 5);
    const again = await restart(bought(1), bought(2, B));
    expect([table(again), table(again, B)]).toEqual([[undefined, 0], [undefined, 0]]);
    expect([shown(again).owned.size, shown(again, B).owned.size]).toEqual([3, 3]);
    expect(calls.map((c) => [c.path, c.body])).toEqual([1, 2].map((id) => ["/api/photocards/open", { box: id }]));
    calls[0]!.answer(answer(opened(), bought(2, B)));
    calls[1]!.answer(answer(opened(), opened(B)));
    await flush();
    expect([again.photoView(A).save!.box, again.photoView(B).save!.box, calls.length]).toEqual([null, null, 2]);
  });

  it("tells the end before the next box of the series is bought, or it would come back", async () => {
    const P = await withBox();
    tear(P, A, 5);
    const pending = P.buyPhotoBox(A);
    await flush();
    // Only the one already on its way.
    expect(paths()).toEqual(["/open"]);
    calls[0]!.answer(answer(opened()));
    await flush();
    expect(paths()).toEqual(["/open", "/buy"]);
    calls[1]!.answer(answer(bought(2, A, { boxes: 2 })));
    expect((await pending)!.id).toBe(2);
  });

  it("tells the end of an earlier start before the first box is bought", async () => {
    const P = await withBox();
    tear(P, A, 5);
    vi.resetModules();
    calls = [];
    (await import("./economy")).setEconomy(ECONOMY);
    const again = await import("./photocards");
    const pending = again.buyPhotoBox(A);
    calls[0]!.answer(answer(bought(1)));
    await flush();
    expect(paths()).toEqual(["", "/open"]);
    calls[1]!.answer(answer(opened()));
    await flush();
    expect(paths()).toEqual(["", "/open", "/buy"]);
    calls[2]!.answer(answer(bought(2)));
    expect((await pending)!.id).toBe(2);
  });

  it("buys nothing of the series while the end cannot be told", async () => {
    const P = await withBox();
    tear(P, A, 5);
    const pending = P.buyPhotoBox(A);
    for (let i = 0; i < 5; i++) {
      calls[i]!.answer(fail(0, "offline"));
      await vi.advanceTimersByTimeAsync(20000);
    }
    expect(await pending).toBeNull();
    expect(P.photoError.value).toBe("无法连接服务器");
    expect(paths()).toEqual(Array(5).fill("/open"));
    expect(P.photoBuying.value).toBe("");
  });

  it("is over when the box was opened on another device", async () => {
    const P = await withBox();
    tear(P, A, 2);
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer(opened()));
    await pending;
    expect([...table(P), P.photoView(A).opening, shown(P).owned.size]).toEqual([undefined, 0, false, 3]);
  });

  it("gives way to the box bought on another device after it", async () => {
    const P = await withBox();
    tear(P, A, 2);
    const pending = P.loadPhotocards();
    calls[0]!.answer(answer(bought(3)));
    await pending;
    expect(table(P)).toEqual([3, 0]);
    // What is still being opened of the other counts for nothing here.
    P.openPhotoBags(A, 1, 5);
    expect([...table(P), calls.length]).toEqual([3, 0, 1]);
  });

  it("stops telling a box that is gone, which does not hold up the next", async () => {
    const P = await withBox();
    tear(P, A, 5);
    calls[0]!.answer(fail(404, "no_box"));
    await vi.advanceTimersByTimeAsync(60000);
    expect(calls).toHaveLength(1);
    const pending = P.buyPhotoBox(A);
    calls[1]!.answer(fail(404, "no_box"));
    await flush();
    expect(paths()).toEqual(["/open", "/open", "/buy"]);
    calls[2]!.answer(answer(bought(2)));
    expect((await pending)!.id).toBe(2);
  });
});

describe("trading", () => {
  const ready: Save = { owned: [SIGN("bella-2")], spare: CFG.swap + 1, boxes: 3 };

  it("trades repeats for a signed card", async () => {
    const P = await store(ready);
    expect(P.photoView(A).canSwap).toBe(true);
    const pending = P.swapPhoto(SIGN("diana-2"));
    expect(P.photoSwapping.value).toBe(true);
    expect(calls[0]).toMatchObject({ method: "POST", path: "/api/photocards/swap", body: { item: SIGN("diana-2") } });
    expect(await P.swapPhoto(SIGN("diana-3"))).toBeNull();
    const owned = [SIGN("bella-2"), SIGN("diana-2")];
    calls[0]!.answer(answer({ ...ready, owned, spare: 1 }, {}, { swapped: SIGN("diana-2") }));
    expect(await pending).toEqual({ item: SIGN("diana-2") });
    expect([shown(P).spare, P.photoView(A).canSwap, P.photoSwapping.value, calls.length]).toEqual([1, false, false, 1]);
  });

  it("trades in the series of the card, whatever goes on in the other", async () => {
    const P = await store(bought(1, A, { spare: 99 }), { ...ready, owned: [], spare: CFG2.swap });
    expect(await P.swapPhoto(SIGN("diana-2"))).toBeNull();
    expect(calls).toEqual([]);
    const pending = P.swapPhoto(SIGN("diana-2", B));
    expect(calls[0]!.body).toEqual({ item: SIGN("diana-2", B) });
    calls[0]!.answer(fail(0, "offline"));
    await flush();
    calls[1]!.answer(answer(bought(1, A, { spare: 99 }), { owned: [SIGN("diana-2", B)] }));
    expect(await pending).toEqual({ item: SIGN("diana-2", B) });
    expect([P.photoError.value, ...table(P)]).toEqual(["", 1, 0]);
  });

  it("goes on while the series is on the shelf but not sold", async () => {
    await shelve({ ...CFG, daily: 0 });
    const P = await store({ ...ready, left: 0 });
    expect(P.photoView(A)).toMatchObject({ canSwap: true, pity: CFG.signPity });
    await shelve(CFG2);
    expect(P.photoView(A)).toMatchObject({ canSwap: false, pity: null, spare: CFG.swap + 1 });
  });

  it("passes on what the last one settled", async () => {
    const P = await store({ ...ready, owned: SIGNS().slice(1) });
    const pending = P.swapPhoto(SIGN("diana-1"));
    calls[0]!.answer(answer({ ...ready, owned: SIGNS(), spare: 0 }, {}, { settled: { cards: 1, shards: 200 } }));
    expect(await pending).toEqual({ item: SIGN("diana-1"), settled: { cards: 1, shards: 200 } });
    expect(P.photoView(A)).toMatchObject({ signsWhole: true, canSwap: false, pity: null });
  });

  it("has nothing to trade for once every signed card is held", async () => {
    const P = await store({ ...ready, owned: SIGNS() });
    expect([P.photoView(A).canSwap, await P.swapPhoto(SIGN("diana-1")), calls.length]).toEqual([false, null, 0]);
  });

  it("asks nothing for a card the save has, or one this build lacks", async () => {
    const P = await store({ ...ready, owned: [SIGN("diana-1")] });
    for (const item of [SIGN("diana-1"), SIGN("nobody-1"), "sign:unknown/diana-1", ""]) {
      expect(await P.swapPhoto(item)).toBeNull();
    }
    expect(calls).toEqual([]);
  });

  it("asks nothing without enough repeats, or with bags left to open", async () => {
    const few = await store({ ...ready, spare: CFG.swap - 1 });
    expect([few.photoView(A).canSwap, await few.swapPhoto(SIGN("diana-1"))]).toEqual([false, null]);
    const pending = few.buyPhotoBox(A);
    calls[0]!.answer(answer(bought(1, A, { spare: CFG.swap + 4 })));
    await pending;
    calls = [];
    expect([few.photoView(A).canSwap, await few.swapPhoto(SIGN("diana-1"))]).toEqual([false, null]);
    expect(calls).toEqual([]);
    tear(few, A, 5);
    expect(few.photoView(A).canSwap).toBe(true);
  });

  it("finds a trade whose answer was lost, and says so when it was not made", async () => {
    const P = await store(ready);
    const made = P.swapPhoto(SIGN("diana-2"));
    calls[0]!.answer(fail(0, "offline"));
    await flush();
    calls[1]!.answer(answer({ ...ready, owned: [SIGN("diana-2")], spare: CFG.swap }));
    expect(await made).toEqual({ item: SIGN("diana-2") });
    expect(P.photoError.value).toBe("");
    calls = [];
    const not = P.swapPhoto(SIGN("diana-3"));
    calls[0]!.answer(fail(0, "offline"));
    await flush();
    calls[1]!.answer(answer({ ...ready, spare: CFG.swap }));
    expect(await not).toBeNull();
    expect(P.photoError.value).toBe("无法连接服务器");
  });

  it("shows the server's words for a refusal", async () => {
    const P = await store(ready);
    const pending = P.swapPhoto(SIGN("diana-2"));
    calls[0]!.answer(fail(409, "owned", "已经有这张签名卡了"));
    expect(await pending).toBeNull();
    expect(P.photoError.value).toBe("已经有这张签名卡了");
    expect(calls).toHaveLength(1);
  });
});

describe("following the save", () => {
  it("starts afresh with another save and drops answers of the last", async () => {
    const P = await store(bought(1, A, { left: 1 }));
    const pending = P.buyPhotoBox(B);
    player.status.value = { player: "B" };
    await flush();
    expect([P.photoState.value, P.photoBuying.value, table(P)]).toEqual([null, "", [undefined, 0]]);
    calls[0]!.answer(answer(bought(1), bought(9, B)));
    expect(await pending).toBeNull();
    expect([P.photoState.value, table(P), table(P, B)]).toEqual([null, [undefined, 0], [undefined, 0]]);
    // The new save's are loaded at once.
    expect(paths()).toEqual(["/buy", ""]);
    calls[1]!.answer(answer({ left: 3 }));
    await flush();
    expect(P.photoState.value!.series[A]!.left).toBe(3);
  });

  it("buys for another save while a purchase of the last is on its way", async () => {
    const P = await store();
    const last = P.buyPhotoBox(A);
    player.status.value = { player: "B" };
    await flush();
    calls[1]!.answer(answer());
    await flush();
    const mine = P.buyPhotoBox(B);
    calls[0]!.answer(answer(bought(9)));
    expect(await last).toBeNull();
    // The end of the last save's purchase is not the end of this one.
    expect(P.photoBuying.value).toBe(B);
    calls[2]!.answer(answer({}, bought(5, B)));
    expect((await mine)!.id).toBe(5);
    expect([P.photoBuying.value, table(P), table(P, B)]).toEqual(["", [undefined, 0], [5, 0]]);
  });

  it("buys nothing for a save that comes as the end of the last one's box is told", async () => {
    const P = await withBox();
    tear(P, A, 5);
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(answer(opened()));
    player.status.value = { player: "B" };
    expect(await pending).toBeNull();
    await flush();
    expect(paths()).toEqual(["/open", ""]);
  });

  it("stops telling the last save's boxes", async () => {
    const P = await store(bought(1), bought(2, B));
    tear(P, A, 5);
    tear(P, B, 5);
    for (const c of calls) c.answer(fail(0, "offline"));
    await flush();
    player.status.value = { player: "B" };
    await flush();
    await vi.advanceTimersByTimeAsync(60000);
    expect(paths()).toEqual(["/open", "/open", ""]);
  });

  it("tells a box of another server although one of the same number is still being told", async () => {
    const P = await store(bought(1));
    tear(P, A, 5);
    player.status.value = { player: "B" };
    await flush();
    calls[1]!.answer(answer(bought(1)));
    await flush();
    tear(P, A, 5);
    expect(paths()).toEqual(["/open", "", "/open"]);
    // The end of the first is not the end of the second, which is still on its way.
    calls[0]!.answer(answer(opened()));
    await flush();
    void P.buyPhotoBox(A);
    await flush();
    expect(paths()).toEqual(["/open", "", "/open"]);
    calls[2]!.answer(answer(opened()));
    await flush();
    expect(paths()).toEqual(["/open", "", "/open", "/buy"]);
  });

  it("keeps quiet about an answer the desk calls stale", async () => {
    const P = await store();
    const pending = P.buyPhotoBox(A);
    calls[0]!.answer(fail(0, "stale"));
    expect(await pending).toBeNull();
    expect([P.photoError.value, P.photoBuying.value, calls.length]).toEqual(["", "", 1]);
  });

  it("loads nothing for another save before it was used", async () => {
    await import("./photocards");
    player.status.value = { player: "B" };
    await flush();
    await shelve(CFG2);
    expect(calls).toEqual([]);
  });
});

describe("photoLeft", () => {
  it("counts the server's day and starts over with the next, each series on its own", async () => {
    const P = await store({ left: 0 }, { left: 2 });
    expect([P.photoLeft(A, NOW), P.photoLeft(B, NOW), P.photoLeft(B)]).toEqual([0, 2, 2]);
    // 23:59:59 and midnight in China.
    const midnight = Date.UTC(2026, 11, 1, 16);
    expect([P.photoLeft(A, midnight - 1000), P.photoLeft(B, midnight - 1000)]).toEqual([0, 2]);
    expect([P.photoLeft(A, midnight), P.photoLeft(B, midnight)]).toEqual([CFG.daily, CFG2.daily]);
    P.resetPhotocards();
    expect(P.photoLeft(A, NOW)).toBeNull();
  });

  it("is never more than the series sells now", async () => {
    const P = await store();
    const midnight = Date.UTC(2026, 11, 1, 16);
    await shelve({ ...CFG, daily: 0 }, { ...CFG2, daily: 1 });
    expect([P.photoLeft(A), P.photoLeft(B), P.photoLeft(A, midnight), P.photoLeft(B, midnight)]).toEqual([0, 1, 0, 1]);
    await shelve(CFG2);
    expect([P.photoLeft(A), P.photoLeft(B), P.photoLeft(A, midnight)]).toEqual([0, CFG2.daily, 0]);
  });
});

it("reads what another build left in storage without trusting it", async () => {
  for (const bad of ["nonsense", "{}", "[1,[2,3],[\"x\",1.5]]", "null"]) {
    vi.resetModules();
    stored["asoultappo.photocards.opened.v1"] = bad;
    calls = [];
    (await import("./economy")).setEconomy(ECONOMY);
    expect(table(await store(bought(1)))).toEqual([1, 0]);
  }
});
