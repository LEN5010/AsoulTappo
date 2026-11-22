import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref, type Ref } from "vue";
import type { LinkGame, LinkResult, LinkState } from "./parkLink";

const parkTry = vi.fn();
vi.mock("./park", () => ({ parkTry: (...a: unknown[]) => parkTry(...a) }));
/** The save's status, fresh for each test (doMock): module copies of earlier tests keep watching their own. */
const player = { status: null as unknown as Ref<{ player: string } | null> };

type Reply = { ok: true; data: unknown } | { ok: false; error: { status: number; code: string; message: string; detail: object } };
interface Call { method: string; path: string; body: Record<string, unknown> | undefined; answer: (r: Reply) => void }

let calls: Call[] = [];
const ok = (data: unknown): Reply => ({ ok: true, data });
const fail = (status: number, code: string): Reply => ({ ok: false, error: { status, code, message: code, detail: {} } });
const flush = () => vi.advanceTimersByTimeAsync(0);
const moves = () => calls.filter((c) => c.path === "/api/park/link/move");

// 2×4, shift none: every pair in a row is next to its match.
const BOARD = [0, 0, 1, 1, 1, 1, 0, 0];
function game(over: Partial<LinkGame> = {}): LinkGame {
  return {
    id: 7, level: 1, rows: 2, cols: 4, shift: "none", kinds: ["a", "b"], board: BOARD, seq: 0, cleared: 0, total: 4,
    hints: 2, seconds: 60, deadline: 1_000_000 + 60_000, now: 1_000_000, ...over,
  };
}
const state = (g: LinkGame | null, over: Partial<LinkState> = {}): LinkState => ({ today: [], played: 1, levels: 3, game: g, last: null, ...over });
const result = (over: Partial<LinkResult> = {}): LinkResult => ({ id: 7, level: 1, cleared: 4, total: 4, prize: 60, reason: "clear", ms: 9000, ...over });

async function started(g = game()) {
  const L = await import("./parkLink");
  const pending = L.startLink();
  calls[0]!.answer(ok({ link: state(g) }));
  expect(await pending).toBe(true);
  calls = [];
  return L;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
  vi.resetModules();
  const status = ref<{ player: string } | null>({ player: "A" });
  player.status = status;
  vi.doMock("./player", () => ({ status }));
  calls = [];
  parkTry.mockReset();
  parkTry.mockImplementation((method: string, path: string, body?: Record<string, unknown>) =>
    new Promise<Reply>((answer) => calls.push({ method, path, body, answer })));
});
afterEach(() => vi.useRealTimers());

describe("park link queue", () => {
  it("removes a pair at once and sends the moves one at a time, in order", async () => {
    const L = await started();
    expect(L.playPair(0, 1)).toBe(true);
    expect(L.linkGame.value!.board).toEqual([-1, -1, 1, 1, 1, 1, 0, 0]);
    expect(L.linkGame.value!.cleared).toBe(1);
    expect(L.playPair(2, 3)).toBe(true);
    await flush();
    expect(moves()).toHaveLength(1);
    expect(moves()[0]!.body).toEqual({ game: 7, seq: 0, a: 0, b: 1 });

    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    expect(moves()).toHaveLength(2);
    expect(moves()[1]!.body).toEqual({ game: 7, seq: 1, a: 2, b: 3 });
    moves()[1]!.answer(ok({ seq: 2, cleared: 2 }));
    await flush();
    expect(moves()).toHaveLength(2);
    expect(L.linkGame.value!.board).toEqual([-1, -1, -1, -1, 1, 1, 0, 0]);
  });

  it("keeps a removed tile's id off the board and the others' in place", async () => {
    const L = await started();
    const before = L.linkTiles.value;
    L.playPair(0, 1);
    expect(L.linkTiles.value.slice(0, 2)).toEqual([-1, -1]);
    expect(L.linkTiles.value.slice(2)).toEqual(before.slice(2));
  });

  it("sends a move again with the same number after a failure, backing off", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    moves()[0]!.answer(fail(0, "offline"));
    await flush();
    expect(moves()).toHaveLength(1);
    // A move made while waiting does not jump the queue.
    L.playPair(2, 3);
    await flush();
    expect(moves()).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(400);
    expect(moves()).toHaveLength(2);
    expect(moves()[1]!.body).toEqual({ game: 7, seq: 0, a: 0, b: 1 });
    moves()[1]!.answer(fail(502, "bad_gateway"));
    await vi.advanceTimersByTimeAsync(799);
    expect(moves()).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(moves()[2]!.body).toEqual({ game: 7, seq: 0, a: 0, b: 1 });
    moves()[2]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    expect(moves()[3]!.body).toEqual({ game: 7, seq: 1, a: 2, b: 3 });
  });

  it("drops the queue on bad_seq and takes the server's board", async () => {
    const L = await started();
    L.playPair(0, 1);
    L.playPair(2, 3);
    await flush();
    moves()[0]!.answer(fail(409, "bad_seq"));
    await flush();
    const get = calls.find((c) => c.method === "GET")!;
    expect(get.path).toBe("/api/park/link");
    expect(L.linkSyncing.value).toBe(true);
    expect(L.playPair(4, 5)).toBe(false);
    const server = [-1, -1, 1, 1, 1, 1, 0, 0];
    get.answer(ok({ link: state(game({ board: server, seq: 1, cleared: 1 })) }));
    await flush();
    expect(L.linkGame.value!.board).toEqual(server);
    expect(L.linkGame.value!.cleared).toBe(1);
    expect(L.linkSyncing.value).toBe(false);
    // The queued second move was dropped; the next one is numbered after the server's count.
    expect(moves()).toHaveLength(1);
    L.playPair(2, 3);
    await flush();
    expect(moves()[1]!.body).toEqual({ game: 7, seq: 1, a: 2, b: 3 });
  });

  it("takes the server's board on bad_move too", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    moves()[0]!.answer(fail(409, "bad_move"));
    await flush();
    calls.find((c) => c.method === "GET")!.answer(ok({ link: state(game()) }));
    await flush();
    expect(L.linkGame.value!.board).toEqual(BOARD);
    expect(L.linkGame.value!.cleared).toBe(0);
  });

  it("keeps the local board when a load answers while moves are on their way", async () => {
    const L = await started();
    const load = L.loadLink();
    L.playPair(0, 1);
    await flush();
    calls.find((c) => c.method === "GET")!.answer(ok({ link: state(game({ deadline: 1_070_000, now: 1_000_500 })) }));
    await load;
    expect(L.linkGame.value!.board).toEqual([-1, -1, 1, 1, 1, 1, 0, 0]);
    expect(L.linkGame.value!.deadline).toBe(1_070_000);
    // Even once the move is through, the load sent before it does not take the board back.
    const late = L.loadLink();
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    calls.filter((c) => c.method === "GET")[1]!.answer(ok({ link: state(game({ board: [-1, -1, 1, 1, 1, 1, 0, 0], seq: 1, cleared: 1 })) }));
    await late;
    expect(L.linkGame.value!.board).toEqual([-1, -1, 1, 1, 1, 1, 0, 0]);
  });

  it("waits for the server's shuffle when no pair is left, then takes it", async () => {
    // 4×3: the 0 in the middle is walled in once the 8s go; nothing else matches.
    const board = [5, 1, 6, 2, 0, 3, 7, 4, 0, 8, 9, 8];
    const L = await started(game({ rows: 4, cols: 3, board, total: 6 }));
    L.playPair(9, 11);
    expect(L.linkShuffling.value).toBe(true);
    expect(L.playPair(4, 8)).toBe(false);
    await flush();
    const shuffle = [5, 1, 6, 2, 3, 0, 7, 4, 0, -1, 9, -1];
    moves()[0]!.answer(ok({ seq: 1, cleared: 1, shuffle }));
    await flush();
    expect(L.linkShuffling.value).toBe(false);
    expect(L.linkGame.value!.board).toEqual(shuffle);
  });

  it("takes the server's board when the board is stuck here but the answer has no shuffle", async () => {
    const board = [5, 1, 6, 2, 0, 3, 7, 4, 0, 8, 9, 8];
    const L = await started(game({ rows: 4, cols: 3, board, total: 6 }));
    L.playPair(9, 11);
    await flush();
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    expect(calls.some((c) => c.method === "GET")).toBe(true);
  });

  it("shows the result and drops the queue when an answer settles the game", async () => {
    const L = await started();
    L.playPair(0, 1);
    L.playPair(2, 3);
    await flush();
    const done = result({ cleared: 1, prize: 3, reason: "time" });
    moves()[0]!.answer(ok({ settled: true, link: state(null, { last: done, today: [done] }), result: done }));
    await flush();
    expect(L.linkResult.value).toEqual(done);
    expect(L.linkPlaying.value).toBe(false);
    expect(L.linkShownResult.value).toEqual(done);
    expect(moves()).toHaveLength(1);
  });
});

describe("park link finish and clock", () => {
  it("sends the queued moves before ending the game", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    const ending = L.finishLink();
    expect(L.linkFinishing.value).toBe(true);
    expect(L.playPair(2, 3)).toBe(false);
    await flush();
    expect(calls.some((c) => c.path === "/api/park/link/finish")).toBe(false);
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    const finish = calls.find((c) => c.path === "/api/park/link/finish")!;
    expect(finish.body).toEqual({ game: 7 });
    const done = result({ cleared: 1, prize: 3, reason: "quit" });
    finish.answer(ok({ link: state(null, { last: done, today: [done] }), result: done }));
    expect(await ending).toBe(true);
    expect(L.linkResult.value).toEqual(done);
    expect(L.linkFinishing.value).toBe(false);
  });

  it("tries the end again when it gets no answer", async () => {
    const L = await started();
    const ending = L.finishLink();
    await flush();
    calls[0]!.answer(fail(0, "offline"));
    await vi.advanceTimersByTimeAsync(400);
    const done = result({ cleared: 0, prize: 0, reason: "quit" });
    calls[1]!.answer(ok({ link: state(null, { last: done }), result: done }));
    expect(await ending).toBe(true);
  });

  it("sets the clock by the server's time when the answer arrives, however long the request waited", async () => {
    const L = await import("./parkLink");
    const pending = L.startLink();
    vi.setSystemTime(1_008_000);
    calls[0]!.answer(ok({ link: state(game({ now: 1_008_000, deadline: 1_068_000 })) }));
    await pending;
    expect(L.linkOffset.value).toBe(0);
    expect(L.serverNow()).toBe(1_008_000);
  });

  it("counts hints per game", async () => {
    const L = await started();
    expect(L.linkHintsLeft.value).toBe(2);
    expect(L.takeHint()).toEqual([0, 1]);
    expect(L.takeHint()).not.toBeNull();
    expect(L.linkHintsLeft.value).toBe(0);
    expect(L.takeHint()).toBeNull();
  });

  it("notices a game settled elsewhere on load", async () => {
    const L = await started();
    const load = L.loadLink();
    const done = result({ cleared: 0, prize: 0, reason: "time" });
    calls[0]!.answer(ok({ link: state(null, { last: done, today: [done] }) }));
    await load;
    expect(L.linkResult.value).toEqual(done);
  });
});

describe("park link races (audit)", () => {
  const get = () => calls.filter((c) => c.method === "GET").at(-1)!;
  const gets = () => calls.filter((c) => c.method === "GET");
  const finishes = () => calls.filter((c) => c.path === "/api/park/link/finish");
  const starts = () => calls.filter((c) => c.path === "/api/park/link/start");
  async function load(L: Awaited<ReturnType<typeof started>>, s: LinkState) {
    const p = L.loadLink();
    get().answer(ok({ link: s }));
    await p;
  }

  it("1: drops an old game's queue and retry when another game comes onto the board", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    moves()[0]!.answer(fail(0, "offline"));
    await flush();
    await load(L, state(game({ id: 8 })));
    await vi.advanceTimersByTimeAsync(10_000);
    expect(moves()).toHaveLength(1);
    expect(L.linkGame.value!.id).toBe(8);
    expect(L.linkGame.value!.board).toEqual(BOARD);
    L.playPair(0, 1);
    await flush();
    expect(moves()[1]!.body).toEqual({ game: 8, seq: 0, a: 0, b: 1 });
  });

  it("2: merges a start answer for the game already on the board and keeps its queue", async () => {
    const L = await import("./parkLink");
    await load(L as never, state(null, { played: 0 }));
    const loading = L.loadLink();
    const starting = L.startLink();
    gets()[1]!.answer(ok({ link: state(game()) }));
    await loading;
    L.playPair(0, 1);
    L.playPair(2, 3);
    starts()[0]!.answer(ok({ link: state(game()) }));
    await starting;
    expect(L.linkGame.value!.cleared).toBe(2);
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    expect(moves()[1]!.body).toEqual({ game: 7, seq: 1, a: 2, b: 3 });
    moves()[1]!.answer(ok({ seq: 2, cleared: 2 }));
    await flush();
    L.playPair(4, 5);
    await flush();
    expect(moves()[2]!.body).toEqual({ game: 7, seq: 2, a: 4, b: 5 });
  });

  it("3: a stale move answer neither releases the new sender nor touches the new queue", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    L.resetLink();
    await load(L, state(game({ id: 8 })));
    L.playPair(0, 1);
    L.playPair(2, 3);
    await flush();
    expect(moves()).toHaveLength(2);
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    // Game 8's first move is still on its way: nothing else goes out.
    expect(moves()).toHaveLength(2);
    moves()[1]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    expect(moves()[2]!.body).toEqual({ game: 8, seq: 1, a: 2, b: 3 });
  });

  it("3: a stale start answer does not replace the next save's game", async () => {
    const L = await import("./parkLink");
    const first = L.startLink();
    L.resetLink();
    const second = L.startLink();
    starts()[1]!.answer(ok({ link: state(game({ id: 8 })) }));
    await second;
    starts()[0]!.answer(ok({ link: state(game({ id: 7 })) }));
    await first;
    expect(L.linkGame.value!.id).toBe(8);
  });

  it("3: an old game's sleeping finish does not clear the next game's", async () => {
    const L = await started();
    const old = L.finishLink();
    await flush();
    finishes()[0]!.answer(fail(0, "offline"));
    await flush();
    L.resetLink();
    await load(L, state(game({ id: 8 })));
    void L.finishLink();
    await flush();
    await vi.advanceTimersByTimeAsync(400);
    await old;
    expect(L.linkFinishing.value).toBe(true);
    expect(L.playPair(0, 1)).toBe(false);
  });

  it("4: another player starts afresh and loads at once, also through no player", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    player.status.value = null;
    await flush();
    expect(L.linkGame.value).toBe(null);
    player.status.value = { player: "B" };
    await flush();
    expect(gets()).toHaveLength(1);
    // The old move's answer changes nothing.
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    get().answer(ok({ link: state(game({ id: 9 })) }));
    await flush();
    expect(L.linkGame.value!.id).toBe(9);
    expect(L.linkGame.value!.board).toEqual(BOARD);
  });

  it("6: a failed resync keeps the board blocked and keeps trying", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    moves()[0]!.answer(fail(409, "bad_move"));
    await flush();
    for (const ms of [400, 800, 1600, 3200, 5000, 5000, 5000]) {
      get().answer(fail(0, "offline"));
      await vi.advanceTimersByTimeAsync(ms);
    }
    expect(L.linkSyncing.value).toBe(true);
    expect(L.playPair(2, 3)).toBe(false);
    get().answer(ok({ link: state(game()) }));
    await flush();
    expect(L.linkSyncing.value).toBe(false);
    expect(L.linkGame.value!.board).toEqual(BOARD);
  });

  it("7: takes a snapshot that is past the whole queue and drops the queue", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    moves()[0]!.answer(fail(0, "offline"));
    await flush();
    const newer = game({ seq: 2, cleared: 2, board: [-1, -1, -1, -1, 1, 1, 0, 0] });
    await load(L, state(newer));
    expect(L.linkGame.value!.board).toEqual(newer.board);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(moves()).toHaveLength(1);
    L.playPair(4, 5);
    await flush();
    expect(moves()[1]!.body).toEqual({ game: 7, seq: 2, a: 4, b: 5 });
  });

  it("7: ignores a snapshot older than the moves accepted", async () => {
    const L = await started();
    L.playPair(0, 1);
    const p = L.loadLink();
    await flush();
    moves()[0]!.answer(ok({ seq: 1, cleared: 1 }));
    await flush();
    get().answer(ok({ link: state(game({ seq: 0 })) }));
    await p;
    expect(L.linkGame.value!.board[0]).toBe(-1);
    L.playPair(2, 3);
    await flush();
    expect(moves()[1]!.body).toMatchObject({ seq: 1 });
  });

  it("8: an end asked for holds through a resync of the same game", async () => {
    const L = await started();
    L.playPair(0, 1);
    await flush();
    const ending = L.finishLink();
    moves()[0]!.answer(fail(409, "bad_seq"));
    await flush();
    expect(L.linkFinishing.value).toBe(true);
    get().answer(ok({ link: state(game({ seq: 1, cleared: 1, board: [-1, -1, 1, 1, 1, 1, 0, 0] })) }));
    await flush();
    expect(finishes()).toHaveLength(1);
    const done = result({ cleared: 1, prize: 3, reason: "quit" });
    finishes()[0]!.answer(ok({ link: state(null, { last: done, today: [done] }), result: done }));
    expect(await ending).toBe(true);
    expect(L.linkResult.value).toEqual(done);
  });

  it("9: a result that does not match the board shows without it; closing it takes the game in play", async () => {
    const L = await started();
    L.playPair(0, 1);
    L.playPair(2, 3);
    await flush();
    const done = result({ cleared: 0, prize: 0, reason: "time" });
    moves()[0]!.answer(ok({ settled: true, result: done, link: state(game({ id: 8 }), { last: done, today: [done] }) }));
    await flush();
    expect(L.linkResult.value).toEqual(done);
    expect(L.linkGame.value).toBe(null);
    L.dismissResult();
    expect(L.linkGame.value!.id).toBe(8);
    expect(L.linkPlaying.value).toBe(true);
  });

  it("10: a start that gets no answer looks for the game at once", async () => {
    const L = await import("./parkLink");
    await load(L as never, state(null, { played: 0 }));
    const p = L.startLink();
    starts()[0]!.answer(fail(0, "desktop"));
    await flush();
    expect(gets()).toHaveLength(2);
    get().answer(ok({ link: state(game()) }));
    expect(await p).toBe(true);
    expect(L.linkGame.value!.id).toBe(7);
    expect(L.linkError.value).toBe("");
  });

  it("11: keeps hints per save", async () => {
    const L = await started();
    L.takeHint();
    L.takeHint();
    expect(L.linkHintsLeft.value).toBe(0);
    player.status.value = { player: "B" };
    await flush();
    get().answer(ok({ link: state(game()) }));
    await flush();
    expect(L.linkHintsLeft.value).toBe(2);
    player.status.value = { player: "A" };
    await flush();
    get().answer(ok({ link: state(game()) }));
    await flush();
    expect(L.linkHintsLeft.value).toBe(0);
  });

  it("12: shows an unseen last result from any day, until closed once seen", async () => {
    const L = await import("./parkLink");
    const r = result({ id: 31 });
    await load(L as never, state(null, { played: 0, last: r, today: [] }));
    expect(L.linkShownResult.value).toEqual(r);
    L.showResult(r);
    await load(L as never, state(null, { played: 0, last: r, today: [] }));
    expect(L.linkShownResult.value).toEqual(r);
    L.dismissResult();
    expect(L.linkShownResult.value).toBe(null);
  });
});
