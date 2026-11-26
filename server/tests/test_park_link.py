"""连连看 in the park (app/park_link.py): fee, daily games, moves, server-side shuffle and settlement."""
import json
import random
import time

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import economy
from app.cards import DropConfig
from app.game import DAY_OFFSET, SCRATCH_DAYS, Game, GameError
from app.link import EMPTY, connect, find_pair, remove_pair
from app.manifest import Manifest
from app.park import LINK_FEE, LINK_PRIZE, Park
from app.park_link import LINK_CLAIM_SLACK_MS, ParkLink
from app.store import Store, day_of
from fixtures import Clock, tiny_manifest

TOKEN = "park-link-player-token-01"
OTHER = "park-link-player-token-02"
M = Manifest.load()
CFG = M.park["link"]
LEVELS = CFG["levels"]
ENTRY = CFG["entry"]
SHARDS = 10_000


def setup(shards=SHARDS, taps=None, require_account=False, seed=7, cfg=None):
    """A save with [shards] and the park open (unless [taps] says otherwise); the rng is seeded. [cfg]: the
    anti-cheat settings, the defaults when None."""
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), cfg, rng=random.Random(seed), now=clock)
    park = Park(lambda: g)
    pl = ParkLink(park, require_account=lambda: require_account)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, shards=shards, taps_total=M.park["coin"]["minTaps"] if taps is None else taps,
                          gift_day=day_of(clock()))
    return g, pl, clock, pid


def ledger(g, pid):
    rows = g.store._db.execute("SELECT day, source, amount, count FROM shard_ledger WHERE player_id = ? "
                               "AND source LIKE 'park_link%' ORDER BY source", (pid,)).fetchall()
    return [tuple(r) for r in rows]


def shards(g, pid):
    return g.store.get_player(pid, 0)["shards"]


def next_midnight(t: float) -> float:
    return ((t + DAY_OFFSET) // 86400 + 1) * 86400 - DAY_OFFSET


def prize(level: dict, cleared: int, total: int) -> int:
    return level["max"] * cleared ** 2 // total ** 2


def play_pair(pl, game, board, seq, clock=None, t=None):
    """Clears the first pair find_pair gives on [board], a second after the last when [clock] is given, claiming [t];
    returns (reply, board after it, as the client keeps it)."""
    if clock is not None:
        clock.t += 1
    a, b = find_pair(board, game["rows"], game["cols"])
    reply = pl.move(TOKEN, game["id"], seq, a, b, t)
    if reply.get("settled"):
        return reply, None
    after = remove_pair(board, game["rows"], game["cols"], game["shift"], a, b)
    return reply, reply.get("shuffle", after)


def stuck_game(g, pid, now):
    """A 4×6 game of three pairs: kind 0 side by side at (0,4) and (0,5), kinds 1 and 2 in a 2×2 checker at (1,1) to
    (2,2), which nothing connects once kind 0 is gone."""
    board = [EMPTY] * 24
    board[4] = board[5] = 0
    board[7] = board[14] = 1
    board[8] = board[13] = 2
    gid = g.store.add_park_link(pid, day_of(now), 1, 4, 6, "none", json.dumps(["a", "b", "c"]), json.dumps(board), 3,
                                LEVELS[0]["max"], now, now + 60)
    return gid, board


# ----------------------------------------------------------------------- config
def test_the_example_config_is_the_contract_example():
    assert {k: v for k, v in CFG.items() if k != "levels"} == {
        "entry": 50, "grace": 3, "account": False,
        "sets": ["jiaran-eat", "nailin-tavern-2025", "beila-adventure-2025", "symphony-xinyi", "symphony-sinuo",
                 "achao"]}
    assert [(lv["rows"], lv["cols"], lv["kinds"], lv["seconds"], lv["shift"], lv["max"], lv["hints"])
            for lv in LEVELS] == [(4, 6, 6, 60, "none", 60, 3), (6, 8, 12, 90, "down", 90, 2),
                                  (6, 10, 15, 120, "center", 120, 1)]
    economy.check_link(CFG, M.data["emoteSets"])


@pytest.mark.parametrize("change,match", [
    (lambda c: c["levels"][0].update(kinds=5), "kinds × 4"),
    (lambda c: c["levels"][0].update(shift="up"), "shift"),
    (lambda c: c["levels"][2].update(cols=5, rows=12), "even"),
    (lambda c: c.update(levels=[]), "at least one"),
    (lambda c: c.update(entry=0), "entry"),
    (lambda c: c.update(grace=True), "grace"),
    (lambda c: c["levels"][1].update(seconds=1.5), "seconds"),
    (lambda c: c["levels"][1].update(hints=0), "hints"),
    (lambda c: c.update(account="yes"), "account"),
])
def test_a_link_config_that_cannot_be_played_is_refused(change, match):
    cfg = json.loads(json.dumps(CFG))
    change(cfg)
    with pytest.raises(ValueError, match=match):
        economy.check_link(cfg)


def test_the_emote_sets_must_exist_and_hold_enough_static_emotes():
    cfg = {**CFG, "sets": ["nope"]}
    economy.check_link(cfg)  # without the manifest only the shape is checked
    with pytest.raises(ValueError, match="nope"):
        economy.check_link(cfg, M.data["emoteSets"])
    # animated emotes do not count
    with pytest.raises(ValueError, match="static"):
        economy.check_link({**CFG, "sets": ["jiaran-moon-motion"]}, M.data["emoteSets"])
    with pytest.raises(ValueError, match="static"):
        economy.check_link({**CFG, "sets": ["symphony-xinyi"]}, M.data["emoteSets"])


def test_the_economy_file_refuses_a_bad_link(tmp_path):
    raw = json.loads(economy.EXAMPLE.read_text(encoding="utf-8"))
    raw["park"]["link"]["levels"][0]["kinds"] = 7
    path = tmp_path / "economy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="kinds"):
        economy.load(path)


def test_the_link_needs_the_park_coin_min_taps():
    raw = json.loads(economy.EXAMPLE.read_text(encoding="utf-8"))
    economy.check(raw)
    del raw["park"]["coin"]["minTaps"]
    with pytest.raises(ValueError, match="minTaps"):
        economy.check(raw)
    del raw["park"]["coin"]
    raw["doudizhu"].pop("counter", None)  # it needs park.coin too, and says so first
    with pytest.raises(ValueError, match="minTaps"):
        economy.check(raw)


def test_the_client_gets_the_link_config():
    got = TestClient(main.app).get("/api/economy").json()
    assert got["park"]["link"] == CFG


# ------------------------------------------------------------------------ start
def test_start_takes_the_fee_and_lays_the_first_level():
    g, pl, clock, pid = setup()
    out = pl.start(TOKEN)
    game = out["link"]["game"]
    level = LEVELS[0]
    assert out["shards"] == SHARDS - ENTRY and shards(g, pid) == SHARDS - ENTRY
    assert ledger(g, pid) == [(day_of(clock()), LINK_FEE, -ENTRY, 1)]
    assert {k: game[k] for k in ("level", "rows", "cols", "shift", "seq", "cleared", "total", "hints", "seconds")} == {
        "level": 1, "rows": level["rows"], "cols": level["cols"], "shift": level["shift"], "seq": 0, "cleared": 0,
        "total": level["rows"] * level["cols"] // 2, "hints": level["hints"], "seconds": level["seconds"]}
    assert game["now"] == round(clock() * 1000) and game["deadline"] == round((clock() + level["seconds"]) * 1000)
    # kinds distinct static emotes of the configured sets, each on four tiles
    static = {e["key"] for s in M.data["emoteSets"] if s["id"] in CFG["sets"] for e in s["emotes"]
              if not e.get("animated")}
    assert len(game["kinds"]) == level["kinds"] == len(set(game["kinds"])) and set(game["kinds"]) <= static
    assert sorted(game["board"]) == sorted(list(range(level["kinds"])) * 4)
    assert find_pair(game["board"], level["rows"], level["cols"])
    assert out["link"]["played"] == 1 and out["link"]["levels"] == len(LEVELS)
    assert out["link"]["today"] == [] and out["link"]["last"] is None
    assert out["park"]["today"]["spent"] == ENTRY


def test_start_with_a_game_in_play_hands_it_back_free():
    g, pl, clock, pid = setup()
    first = pl.start(TOKEN)["link"]["game"]
    clock.t += 10
    again = pl.start(TOKEN)["link"]
    assert again["game"]["id"] == first["id"] and again["game"]["board"] == first["board"]
    assert again["played"] == 1 and shards(g, pid) == SHARDS - ENTRY
    assert ledger(g, pid) == [(day_of(clock()), LINK_FEE, -ENTRY, 1)]


def test_start_needs_the_park_open():
    g, pl, _, pid = setup(taps=M.park["coin"]["minTaps"] - 1)
    with pytest.raises(GameError) as e:
        pl.start(TOKEN)
    assert e.value.code == "park_locked" and shards(g, pid) == SHARDS and ledger(g, pid) == []


def test_start_needs_the_entry_fee():
    g, pl, _, pid = setup(shards=ENTRY - 1)
    with pytest.raises(GameError) as e:
        pl.start(TOKEN)
    assert e.value.code == "no_shards" and shards(g, pid) == ENTRY - 1
    assert pl.state(TOKEN)["link"]["played"] == 0
    g.store.update_player(pid, shards=ENTRY)
    assert pl.start(TOKEN)["shards"] == 0


def test_the_account_switch_needs_a_linked_save_on_a_server_with_accounts():
    g, pl, clock, pid = setup(require_account=True)
    other = g.status(OTHER)["player"]
    g.store.update_player(other, shards=SHARDS, taps_total=M.park["coin"]["minTaps"])
    pl.start(OTHER)  # the switch is off in the example
    g.manifest.park["link"]["account"] = True
    with pytest.raises(GameError) as e:
        pl.start(TOKEN)
    assert e.value.code == "account_required" and shards(g, pid) == SHARDS
    g.store.link_account("main-user-1", pid, clock())
    assert pl.start(TOKEN)["link"]["game"]["level"] == 1
    # a server without main-site accounts has no saves to link: the switch does nothing there
    g3, pl3, _, _ = setup(require_account=False)
    g3.manifest.park["link"]["account"] = True
    assert pl3.start(TOKEN)["link"]["game"]["level"] == 1


def test_the_day_has_len_levels_games_each_harder():
    g, pl, clock, pid = setup()
    for n, level in enumerate(LEVELS, 1):
        game = pl.start(TOKEN)["link"]["game"]
        assert (game["level"], game["rows"], game["cols"], game["shift"]) == \
            (n, level["rows"], level["cols"], level["shift"])
        out = pl.finish(TOKEN, game["id"])
        assert out["result"]["reason"] == "quit" and out["link"]["played"] == n
    with pytest.raises(GameError) as e:
        pl.start(TOKEN)
    assert e.value.code == "link_done"
    assert shards(g, pid) == SHARDS - ENTRY * len(LEVELS)
    assert ledger(g, pid) == [(day_of(clock()), LINK_FEE, -ENTRY * len(LEVELS), len(LEVELS))]
    state = pl.state(TOKEN)["link"]
    assert [r["level"] for r in state["today"]] == [1, 2, 3] and state["game"] is None
    assert state["last"]["level"] == 3


def test_an_abandoned_game_counts_and_is_settled_by_the_next_start():
    g, pl, clock, pid = setup()
    first = pl.start(TOKEN)["link"]["game"]
    clock.t += LEVELS[0]["seconds"] + CFG["grace"] + 1
    out = pl.start(TOKEN)["link"]
    assert out["game"]["level"] == 2 and out["played"] == 2
    assert out["today"] == [{"id": first["id"], "level": 1, "cleared": 0, "total": first["total"], "prize": 0,
                             "reason": "time", "ms": LEVELS[0]["seconds"] * 1000}]


def test_a_refused_start_keeps_the_settlement_of_an_expired_game():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    g.store.update_player(pid, shards=0)
    clock.t += LEVELS[0]["seconds"] + CFG["grace"] + 1
    with pytest.raises(GameError) as e:
        pl.start(TOKEN)
    assert e.value.code == "no_shards"
    assert g.store.park_link_game(pid, game["id"])["reason"] == "time"


def test_games_count_on_the_day_they_start():
    g, pl, clock, pid = setup()
    midnight = next_midnight(clock())
    clock.t = midnight - 5
    for _ in LEVELS[:-1]:
        pl.finish(TOKEN, pl.start(TOKEN)["link"]["game"]["id"])
    late = pl.start(TOKEN)["link"]["game"]
    assert late["level"] == len(LEVELS)
    # past midnight the game of yesterday is still in play: no new game, and today counts none of yesterday's
    clock.t = midnight + 1
    out = pl.state(TOKEN)["link"]
    assert out["game"]["id"] == late["id"] and out["played"] == 0 and out["today"] == []
    assert pl.start(TOKEN)["link"]["game"]["id"] == late["id"]
    # once it is past its time, the next start settles it and plays the first level of the new day
    clock.t = midnight - 5 + LEVELS[-1]["seconds"] + CFG["grace"] + 1
    out = pl.start(TOKEN)["link"]
    assert out["game"]["level"] == 1 and out["played"] == 1 and out["last"]["id"] == late["id"]
    days = {r[0] for r in ledger(g, pid)}
    assert days == {day_of(midnight - 5), day_of(midnight + 1)}


def test_the_board_is_laid_again_when_the_level_moved_while_it_was_laid():
    g, pl, clock, pid = setup()
    real = pl._lay
    calls = []

    def lay(n):
        calls.append(n)
        if len(calls) == 1:
            # another start of the same save sneaks in while the first board is laid
            g.store.add_park_link(pid, day_of(clock()), 1, 4, 6, "none", "[]", "[]", 12, 1, clock(),
                                  clock() - 100)
            g.store.settle_park_link(g.store.park_link_active(pid)["id"], 0, "quit", clock())
        return real(n)

    pl._lay = lay
    game = pl.start(TOKEN)["link"]["game"]
    assert calls == [0, 1] and game["level"] == 2 and shards(g, pid) == SHARDS - ENTRY


# ------------------------------------------------------------------------ moves
def test_a_move_answers_little_and_a_resend_answers_the_same():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board = game["board"]
    a, b = find_pair(board, game["rows"], game["cols"])
    clock.t += 1.5
    reply = pl.move(TOKEN, game["id"], 0, a, b)
    assert reply == {"seq": 1, "cleared": 1}
    assert pl.move(TOKEN, game["id"], 0, a, b) == reply
    assert pl.move(TOKEN, game["id"], 0, b, a) == reply  # a pair either way round
    row = g.store.park_link_game(pid, game["id"])
    assert json.loads(row["events"]) == [{"a": a, "b": b, "t": 1500, "c": 1500}] and row["cleared"] == 1
    assert json.loads(row["board"]) == remove_pair(board, game["rows"], game["cols"], game["shift"], a, b)
    assert json.loads(row["board0"]) == board


def test_a_move_encodes_the_board_and_the_events_once(monkeypatch):
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    import app.park_link as park_link
    dumps = []
    dump = park_link._dump
    monkeypatch.setattr(park_link, "_dump", lambda v: dumps.append(v) or dump(v))
    clock.t += 1
    play_pair(pl, game, game["board"], 0)
    assert len(dumps) == 2


def test_a_resend_of_another_pair_or_a_gap_is_bad_seq():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    reply, board = play_pair(pl, game, game["board"], 0)
    a, b = find_pair(board, game["rows"], game["cols"])
    for seq, pair in ((0, (a, b)), (2, (a, b)), (-1, (a, b))):
        with pytest.raises(GameError) as e:
            pl.move(TOKEN, game["id"], seq, *pair)
        assert e.value.code == "bad_seq"
    assert pl.move(TOKEN, game["id"], 1, a, b)["seq"] == 2


def test_a_move_the_board_does_not_allow_is_bad_move():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    rows, cols = game["rows"], game["cols"]
    board = game["board"]
    a, b = find_pair(board, rows, cols)
    other = next(i for i in range(len(board)) if board[i] != board[a])
    blocked = next(((i, j) for i in range(len(board)) for j in range(i + 1, len(board))
                    if board[i] == board[j] and not connect(board, rows, cols, i, j)), None)
    bad = [(a, a), (a, other), (-1, b), (a, rows * cols), (a, 10_000)]
    if blocked:
        bad.append(blocked)
    for x, y in bad:
        with pytest.raises(GameError) as e:
            pl.move(TOKEN, game["id"], 0, x, y)
        assert e.value.code == "bad_move", (x, y)
    pl.move(TOKEN, game["id"], 0, a, b)
    with pytest.raises(GameError) as e:  # a cell emptied by the last pair
        pl.move(TOKEN, game["id"], 1, a, b)
    assert e.value.code == "bad_move"
    assert g.store.park_link_game(pid, game["id"])["cleared"] == 1


def test_another_saves_game_is_no_game():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    g.status(OTHER)
    for call in (lambda: pl.move(OTHER, game["id"], 0, 0, 1), lambda: pl.finish(OTHER, game["id"]),
                 lambda: pl.move(TOKEN, 999, 0, 0, 1)):
        with pytest.raises(GameError) as e:
            call()
        assert e.value.code == "no_game"


def test_clearing_the_board_settles_with_the_top_prize():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board, seq, reply = game["board"], 0, {}
    while not reply.get("settled"):
        clock.t += 1
        reply, board = play_pair(pl, game, board, seq)
        seq += 1
        assert reply.get("settled") or reply["seq"] == seq
    top = LEVELS[0]["max"]
    assert seq == game["total"]
    assert reply["result"] == {"id": game["id"], "level": 1, "cleared": game["total"], "total": game["total"],
                               "prize": top, "reason": "clear", "ms": game["total"] * 1000}
    assert reply["link"]["game"] is None and reply["link"]["last"] == reply["result"]
    assert reply["shards"] == SHARDS - ENTRY + top
    day = day_of(clock())
    assert ledger(g, pid) == [(day, LINK_PRIZE, top, 1), (day, LINK_FEE, -ENTRY, 1)]
    assert reply["park"]["today"]["spent"] == ENTRY and reply["park"]["today"]["won"] == top
    # the last pair again, or finish: the same result, paid once
    assert pl.move(TOKEN, game["id"], seq - 1, 0, 1)["result"] == reply["result"]
    assert pl.finish(TOKEN, game["id"])["result"] == reply["result"]
    assert shards(g, pid) == SHARDS - ENTRY + top


def test_a_board_left_without_a_pair_is_shuffled_by_the_server():
    g, pl, clock, pid = setup()
    gid, board = stuck_game(g, pid, clock())
    left = remove_pair(board, 4, 6, "none", 4, 5)
    assert not find_pair(left, 4, 6)  # the construction is stuck
    reply = pl.move(TOKEN, gid, 0, 4, 5)
    assert reply["seq"] == 1 and reply["cleared"] == 1
    shuffled = reply["shuffle"]
    assert find_pair(shuffled, 4, 6)
    assert sorted(shuffled) == sorted(left) and [i for i, k in enumerate(shuffled) if k != EMPTY] == \
        [i for i, k in enumerate(left) if k != EMPTY]
    # the resend brings the same shuffle, and the game goes on from it
    assert pl.move(TOKEN, gid, 0, 5, 4) == reply
    row = g.store.park_link_game(pid, gid)
    assert json.loads(row["board"]) == shuffled and json.loads(row["events"])[0]["shuffle"] == shuffled
    assert pl.state(TOKEN)["link"]["game"]["board"] == shuffled
    a, b = find_pair(shuffled, 4, 6)
    assert pl.move(TOKEN, gid, 1, a, b) == {"seq": 2, "cleared": 2}


# ------------------------------------------------------------------------- time
def test_a_game_keeps_the_top_prize_it_started_with():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    top = LEVELS[0]["max"]
    assert g.store.park_link_game(pid, game["id"])["max"] == top
    board = game["board"]
    for seq in range(3):
        _, board = play_pair(pl, game, board, seq, clock)
    g.manifest.park["link"]["levels"][0]["max"] = top * 10
    assert game["max"] == top and pl.state(TOKEN)["link"]["game"]["max"] == top
    assert pl.finish(TOKEN, game["id"])["result"]["prize"] == prize({"max": top}, 3, game["total"])


def test_moves_and_finish_count_from_their_arrival_not_from_the_store_lock():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    start = clock()
    real = g.store.transaction

    def slow():
        # the request waits five seconds for the lock
        clock.t += 5
        return real()

    clock.t = start + LEVELS[0]["seconds"] + CFG["grace"]
    a, b = find_pair(game["board"], game["rows"], game["cols"])
    g.store.transaction = slow
    assert pl.move(TOKEN, game["id"], 0, a, b) == {"seq": 1, "cleared": 1}
    g.store.transaction = real
    event = json.loads(g.store.park_link_game(pid, game["id"])["events"])[0]
    assert event["t"] == (LEVELS[0]["seconds"] + CFG["grace"]) * 1000

    second = pl.start(TOKEN)["link"]["game"]
    clock.t += LEVELS[1]["seconds"] - 1
    g.store.transaction = slow
    out = pl.finish(TOKEN, second["id"])
    g.store.transaction = real
    assert out["result"]["reason"] == "quit" and out["result"]["ms"] == (LEVELS[1]["seconds"] - 1) * 1000


def test_a_prize_goes_on_the_day_the_game_is_settled():
    g, pl, clock, pid = setup()
    midnight = next_midnight(clock())
    clock.t = midnight - 5
    game = pl.start(TOKEN)["link"]["game"]
    board = game["board"]
    for seq in range(3):
        _, board = play_pair(pl, game, board, seq, clock)
    clock.t = midnight + 1
    out = pl.finish(TOKEN, game["id"])
    want = prize(LEVELS[0], 3, game["total"])
    assert out["result"]["reason"] == "quit" and want > 0
    assert out["park"]["today"] == {"spent": 0, "won": want}
    assert ledger(g, pid) == [(day_of(midnight + 1), LINK_PRIZE, want, 1), (day_of(midnight - 5), LINK_FEE, -ENTRY, 1)]


def test_a_move_within_the_grace_counts_and_a_later_one_settles_the_game():
    g, pl, clock, pid = setup()
    out = pl.start(TOKEN)
    game = out["link"]["game"]
    start = clock()
    clock.t = start + LEVELS[0]["seconds"] + CFG["grace"]
    reply, board = play_pair(pl, game, game["board"], 0)
    assert reply == {"seq": 1, "cleared": 1}
    clock.t += 0.01
    a, b = find_pair(board, game["rows"], game["cols"])
    late = pl.move(TOKEN, game["id"], 1, a, b)
    want = prize(LEVELS[0], 1, game["total"])
    assert late["settled"] is True
    assert late["result"] == {"id": game["id"], "level": 1, "cleared": 1, "total": game["total"], "prize": want,
                              "reason": "time", "ms": (LEVELS[0]["seconds"] + CFG["grace"]) * 1000}
    assert g.store.park_link_game(pid, game["id"])["cleared"] == 1
    assert shards(g, pid) == SHARDS - ENTRY + want


def test_get_settles_a_game_past_its_time():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    start = clock()
    board = game["board"]
    for seq in range(4):
        _, board = play_pair(pl, game, board, seq, clock)
    clock.t = start + LEVELS[0]["seconds"] + CFG["grace"]
    assert pl.state(TOKEN)["link"]["game"]["cleared"] == 4  # still within the grace
    clock.t += 1
    link = pl.state(TOKEN)["link"]
    want = prize(LEVELS[0], 4, game["total"])
    assert link["game"] is None and link["last"]["reason"] == "time" and link["last"]["prize"] == want
    assert link["today"] == [link["last"]] and link["last"]["ms"] == 4000
    assert shards(g, pid) == SHARDS - ENTRY + want
    pl.state(TOKEN)
    assert shards(g, pid) == SHARDS - ENTRY + want


def test_finish_before_the_deadline_quits_and_after_it_runs_out_of_time():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board = game["board"]
    for seq in range(3):
        clock.t += 2
        _, board = play_pair(pl, game, board, seq)
    clock.t += 1
    out = pl.finish(TOKEN, game["id"])
    want = prize(LEVELS[0], 3, game["total"])
    assert out["result"] == {"id": game["id"], "level": 1, "cleared": 3, "total": game["total"], "prize": want,
                             "reason": "quit", "ms": 6000}
    assert out["link"]["game"] is None and out["shards"] == SHARDS - ENTRY + want
    # twice: the same result, paid once; a move after it answers the result too
    assert pl.finish(TOKEN, game["id"])["result"] == out["result"]
    assert pl.move(TOKEN, game["id"], 3, 0, 1)["result"] == out["result"]
    assert shards(g, pid) == SHARDS - ENTRY + want
    assert ledger(g, pid) == [(day_of(clock()), LINK_PRIZE, want, 1), (day_of(clock()), LINK_FEE, -ENTRY, 1)]

    second = pl.start(TOKEN)["link"]["game"]
    clock.t += LEVELS[1]["seconds"]
    out = pl.finish(TOKEN, second["id"])
    assert out["result"]["reason"] == "time" and out["result"]["prize"] == 0
    assert out["result"]["ms"] == LEVELS[1]["seconds"] * 1000
    assert out["link"]["today"] == [pl.state(TOKEN)["link"]["today"][0], out["result"]]


def test_a_quit_without_moves_counts_to_the_quit():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 12.5
    assert pl.finish(TOKEN, game["id"])["result"]["ms"] == 12500


def test_park_today_sets_the_fees_against_the_prizes():
    g, pl, clock, pid = setup()
    won = 0
    for n in range(2):
        game = pl.start(TOKEN)["link"]["game"]
        board = game["board"]
        for seq in range(n + 2):
            _, board = play_pair(pl, game, board, seq, clock)
        won += pl.finish(TOKEN, game["id"])["result"]["prize"]
    today = pl.state(TOKEN)["park"]["today"]
    assert today == {"spent": 2 * ENTRY, "won": won} and won > 0
    assert ledger(g, pid) == [(day_of(clock()), LINK_PRIZE, won, 2), (day_of(clock()), LINK_FEE, -2 * ENTRY, 2)]


# --------------------------------------------------------- minimum time per pair
MIN_PAIR = DropConfig().link_min_pair_ms


def events(g, pid, gid):
    return json.loads(g.store.park_link_game(pid, gid)["events"])


def test_an_instant_script_wins_nothing():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board, seq, reply = game["board"], 0, {}
    while not reply.get("settled"):
        reply, board = play_pair(pl, game, board, seq)
        seq += 1
    assert reply["result"]["reason"] == "clear" and reply["result"]["cleared"] == game["total"]
    assert reply["result"]["prize"] == 0 and shards(g, pid) == SHARDS - ENTRY
    evs = events(g, pid, game["id"])
    assert "fast" not in evs[0] and all(ev["fast"] for ev in evs[1:])
    assert "fast" not in json.dumps(reply)


def test_an_instant_script_claiming_spaced_times_wins_nothing():
    # every claim sits within the slack and none is fast, but nothing arrived after the start
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 0.01
    board, seq = game["board"], 0
    while (seq + 1) * MIN_PAIR <= LINK_CLAIM_SLACK_MS:
        _, board = play_pair(pl, game, board, seq, t=(seq + 1) * MIN_PAIR)
        seq += 1
    evs = events(g, pid, game["id"])
    assert seq == LINK_CLAIM_SLACK_MS // MIN_PAIR and not any(ev.get("fast") for ev in evs)
    assert pl.finish(TOKEN, game["id"])["result"]["prize"] == 0


def test_the_first_pair_is_never_fast():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 0.5
    _, board = play_pair(pl, game, game["board"], 0, t=50)
    first = events(g, pid, game["id"])[0]
    assert first["c"] == 50 and first["t"] == 500 and "fast" not in first
    # a claim past the slack is still cut
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 1
    play_pair(pl, game, game["board"], 0, t=60_000)
    assert events(g, pid, game["id"])[0]["c"] == 1000 + LINK_CLAIM_SLACK_MS


def test_a_human_paced_game_pays_in_full():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    start = clock()
    board, seq, reply = game["board"], 0, {}
    while not reply.get("settled"):
        clock.t = start + 2.5 * (seq + 1)
        reply, board = play_pair(pl, game, board, seq, t=round(2500 * (seq + 1) - 200))  # the client's estimate
        seq += 1
    assert reply["result"]["prize"] == LEVELS[0]["max"]


def test_an_idle_script_that_bursts_loses_the_burst():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 30
    board = game["board"]
    for seq in range(6):
        _, board = play_pair(pl, game, board, seq, t=30_000)
    evs = events(g, pid, game["id"])
    assert "fast" not in evs[0] and all(ev["fast"] for ev in evs[1:])
    assert pl.finish(TOKEN, game["id"])["result"]["prize"] == prize(LEVELS[0], 1, game["total"])


def test_claims_spaced_at_the_threshold_win_the_full_prize():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    start = clock()
    board, seq, reply = game["board"], 0, {}
    while not reply.get("settled"):
        clock.t = start + (seq + 1) * MIN_PAIR / 1000
        reply, board = play_pair(pl, game, board, seq, t=(seq + 1) * MIN_PAIR)
        seq += 1
    assert reply["result"]["prize"] == LEVELS[0]["max"]
    assert not any(ev.get("fast") for ev in events(g, pid, game["id"]))


def test_late_arrivals_with_spaced_claims_are_not_fast():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 10  # five pairs played a second apart arrive together, as a queue sent after a stall
    board = game["board"]
    for seq in range(5):
        _, board = play_pair(pl, game, board, seq, t=(seq + 1) * 1000)
    evs = events(g, pid, game["id"])
    assert [ev["c"] for ev in evs] == [1000, 2000, 3000, 4000, 5000] and {ev["t"] for ev in evs} == {10_000}
    assert not any(ev.get("fast") for ev in evs)
    assert pl.finish(TOKEN, game["id"])["result"]["prize"] == prize(LEVELS[0], 5, game["total"])


def test_claims_past_the_arrival_and_slack_are_cut():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 10
    board = game["board"]
    for seq in range(4):
        _, board = play_pair(pl, game, board, seq, t=10_000 + seq * 5000)
    evs = events(g, pid, game["id"])
    top = 10_000 + LINK_CLAIM_SLACK_MS
    assert [ev["c"] for ev in evs] == [10_000, top, top, top]
    assert [bool(ev.get("fast")) for ev in evs] == [False, False, True, True]
    assert pl.finish(TOKEN, game["id"])["result"]["prize"] == prize(LEVELS[0], 2, game["total"])


def test_a_claim_before_the_last_one_is_moved_up_to_it():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board = game["board"]
    for seq, t in enumerate((1000, 500, 3000)):
        _, board = play_pair(pl, game, board, seq, clock, t=t)
    evs = events(g, pid, game["id"])
    assert [ev["c"] for ev in evs] == [1000, 1000, 3000]
    assert [bool(ev.get("fast")) for ev in evs] == [False, True, False]


def test_one_fast_pair_costs_that_pair_only():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board = game["board"]
    for seq in range(8):
        # the sixth pair claims the time of the fifth
        _, board = play_pair(pl, game, board, seq, clock, t=5000 if seq == 5 else None)
    assert [i for i, ev in enumerate(events(g, pid, game["id"])) if ev.get("fast")] == [5]
    result = pl.finish(TOKEN, game["id"])["result"]
    assert result["cleared"] == 8 and result["prize"] == prize(LEVELS[0], 7, game["total"])


def test_a_resend_with_another_time_changes_nothing():
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 2
    a, b = find_pair(game["board"], game["rows"], game["cols"])
    reply = pl.move(TOKEN, game["id"], 0, a, b, 1000)
    before = events(g, pid, game["id"])
    assert before == [{"a": a, "b": b, "t": 2000, "c": 1000}]
    clock.t += 5
    assert pl.move(TOKEN, game["id"], 0, a, b, 0) == reply
    assert pl.move(TOKEN, game["id"], 0, a, b, 6000) == reply
    assert events(g, pid, game["id"]) == before


def test_the_threshold_is_an_anti_cheat_setting():
    assert economy.drop_config({}).link_min_pair_ms == MIN_PAIR == 250
    example = economy.drop_config(Manifest.load().anti_cheat)
    assert example.link_min_pair_ms == 300
    with pytest.raises(ValueError, match="link_min_pair_msec"):
        economy.drop_config({"link_min_pair_msec": 300})
    # the server uses the configured value: 280 ms apart is fast at 300, not at the default
    for cfg, fast in ((example, True), (None, False)):
        g, pl, clock, pid = setup(cfg=cfg)
        game = pl.start(TOKEN)["link"]["game"]
        board = game["board"]
        for seq, t in enumerate((1000, 1280)):
            _, board = play_pair(pl, game, board, seq, clock, t=t)
        assert bool(events(g, pid, game["id"])[1].get("fast")) is fast


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "1", None])
def test_the_threshold_must_be_a_whole_number_of_1_or_more(bad):
    # 0 would divide by zero when a game with pairs is settled.
    with pytest.raises(ValueError, match="link_min_pair_ms"):
        economy.drop_config({"link_min_pair_ms": bad})


def test_the_threshold_stays_on_the_server():
    body = TestClient(main.app).get("/api/economy").text
    assert "link_min_pair_ms" not in body


def test_the_game_tells_its_start():
    g, pl, clock, pid = setup()
    start = clock()
    game = pl.start(TOKEN)["link"]["game"]
    clock.t += 3
    again = pl.state(TOKEN)["link"]["game"]
    assert game["start"] == again["start"] == round(start * 1000) and again["now"] == round((start + 3) * 1000)


# ------------------------------------------------------------------- generation
@pytest.mark.parametrize("n", range(len(LEVELS)))
def test_each_level_lays_a_board_quickly(n):
    g, pl, _, _ = setup(seed=n)
    worst = 0.0
    for _ in range(5):
        t = time.perf_counter()
        kinds, board = pl._lay(n)
        worst = max(worst, time.perf_counter() - t)
        level = LEVELS[n]
        assert len(kinds) == level["kinds"] and sorted(board) == sorted(list(range(level["kinds"])) * 4)
    assert worst < 0.2


# ------------------------------------------------------------------------ store
LINK_INDEXES = ("park_link_open", "park_link_settled")


def plan(st, sql, *args):
    return " | ".join(r["detail"] for r in st._db.execute("EXPLAIN QUERY PLAN " + sql, args).fetchall())


def test_the_game_in_play_and_the_last_result_are_found_by_their_own_indexes():
    g, pl, clock, pid = setup()
    st = g.store
    for day in range(30):
        now = clock() + day * 86400
        for n in range(3):
            gid, _ = stuck_game(g, pid, now + n)
            st.settle_park_link(gid, 0, "quit", now + n + 1)
    stuck_game(g, pid, clock() + 31 * 86400)
    active = plan(st, "SELECT * FROM park_link WHERE player_id = ? AND settled_at IS NULL ORDER BY id DESC LIMIT 1",
                  pid)
    last = plan(st, "SELECT id FROM park_link WHERE player_id = ? AND settled_at IS NOT NULL "
                    "ORDER BY settled_at DESC, id DESC LIMIT 1", pid)
    assert "park_link_open" in active and "TEMP B-TREE" not in active
    assert "park_link_settled" in last and "TEMP B-TREE" not in last


def test_an_older_database_gets_the_link_indexes_when_opened(tmp_path):
    path = str(tmp_path / "old.db")
    st = Store(path)
    for name in LINK_INDEXES:
        st._db.execute(f"DROP INDEX {name}")
    st._db.commit()
    st.close()
    st = Store(path)
    names = {r[0] for r in st._db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    st.close()
    assert set(LINK_INDEXES) <= names


def test_get_reads_the_game_in_play_once(monkeypatch):
    g, pl, clock, pid = setup()
    pl.start(TOKEN)
    reads = []
    active = g.store.park_link_active
    monkeypatch.setattr(g.store, "park_link_active", lambda p: reads.append(p) or active(p))
    assert pl.state(TOKEN)["link"]["game"] is not None
    assert len(reads) == 1


def test_an_answer_is_read_at_one_moment_whatever_another_device_does(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread
    g, pl, clock, pid = setup()
    old = shards(g, pid)
    read = Event()
    status = g.status

    def pausing(token, **kw):
        out = status(token, **kw)
        if current_thread().name.startswith("reader"):
            read.set()
            time.sleep(0.2)  # another device starts a game meanwhile
        return out

    monkeypatch.setattr(g, "status", pausing)
    with ThreadPoolExecutor(1, thread_name_prefix="reader") as reader, \
            ThreadPoolExecutor(1, thread_name_prefix="other") as other:
        answer = reader.submit(pl.state, TOKEN)
        assert read.wait(5)
        started = other.submit(pl.start, TOKEN)
        out = answer.result(5)
        assert started.result(5)["link"]["game"] is not None
    playing = out["link"]["game"] is not None
    assert (out["shards"], out["park"]["today"]["spent"], out["link"]["played"]) == \
        ((old - ENTRY, ENTRY, 1) if playing else (old, 0, 0))
    assert shards(g, pid) == old - ENTRY


# ------------------------------------------------------------------- link off
def played(pairs=3):
    """A save's first game with [pairs] pairs taken a second apart."""
    g, pl, clock, pid = setup()
    game = pl.start(TOKEN)["link"]["game"]
    board = game["board"]
    for seq in range(pairs):
        _, board = play_pair(pl, game, board, seq, clock)
    return g, pl, clock, pid, game, board


def link_off(monkeypatch, g, park=False):
    """Turns the link off (or the whole park, when [park]), as a restart with an economy without it does."""
    if park:
        monkeypatch.setattr(g.manifest, "park", None)
    else:
        monkeypatch.delitem(g.manifest.park, "link")


@pytest.mark.parametrize("call", ["state", "start", "finish", "move"])
def test_with_the_link_off_a_game_paid_for_is_settled_on_its_pairs_and_no_game_starts(monkeypatch, call):
    g, pl, clock, pid, game, board = played()
    before = shards(g, pid)
    link_off(monkeypatch, g)
    a, b = find_pair(board, game["rows"], game["cols"])
    args = {"state": (), "start": (), "finish": (game["id"],), "move": (game["id"], 3, a, b)}[call]
    with pytest.raises(GameError) as e:
        getattr(pl, call)(TOKEN, *args)
    assert e.value.code == "no_park"
    row = g.store.park_link_game(pid, game["id"])
    won = prize(LEVELS[0], 3, game["total"])
    assert won > 0 and row["settled_at"] is not None and (row["reason"], row["cleared"], row["prize"]) == ("quit", 3, won)
    assert shards(g, pid) == before + won
    assert g.store.park_link_played(pid, day_of(clock())) == 1
    # Paid once, whatever comes after.
    for again in ("state", "start", "finish"):
        with pytest.raises(GameError):
            getattr(pl, again)(TOKEN, *({"finish": (game["id"],)}.get(again, ())))
    assert shards(g, pid) == before + won
    assert [r for r in ledger(g, pid) if r[1] == LINK_PRIZE] == [(day_of(clock()), LINK_PRIZE, won, 1)]


def test_with_the_park_off_a_game_past_its_time_is_settled_as_run_out(monkeypatch):
    g, pl, clock, pid, game, _ = played()
    before = shards(g, pid)
    clock.t += 3600
    link_off(monkeypatch, g, park=True)
    with pytest.raises(GameError) as e:
        pl.state(TOKEN)
    assert e.value.code == "no_park"
    row = g.store.park_link_game(pid, game["id"])
    assert (row["reason"], row["prize"]) == ("time", prize(LEVELS[0], 3, game["total"]))
    assert shards(g, pid) == before + row["prize"]


def test_with_the_link_off_another_saves_game_is_left_alone(monkeypatch):
    g, pl, clock, pid, game, _ = played()
    link_off(monkeypatch, g)
    for call, args in ((pl.state, ()), (pl.finish, (game["id"],))):
        with pytest.raises(GameError):
            call(OTHER, *args)
    assert g.store.park_link_game(pid, game["id"])["settled_at"] is None


def test_with_the_link_off_prune_settles_every_game_in_play(monkeypatch):
    g, pl, clock, pid, game, _ = played()
    other = g.status(OTHER)["player"]
    g.store.update_player(other, taps_total=M.park["coin"]["minTaps"], gift_day=day_of(clock()))
    second = pl.start(OTHER)["link"]["game"]
    before = shards(g, pid), shards(g, other)
    link_off(monkeypatch, g)
    assert pl.prune() == 0
    won = prize(LEVELS[0], 3, game["total"])
    assert g.store.park_link_game(pid, game["id"])["prize"] == won
    assert g.store.park_link_game(other, second["id"])["settled_at"] is not None
    assert (shards(g, pid), shards(g, other)) == (before[0] + won, before[1])
    pl.prune()
    assert (shards(g, pid), shards(g, other)) == (before[0] + won, before[1])


def test_with_the_link_on_prune_leaves_games_in_play_alone():
    g, pl, clock, pid, game, _ = played()
    clock.t += 3600
    assert pl.prune() == 0
    assert g.store.park_link_game(pid, game["id"])["settled_at"] is None


# ------------------------------------------------------------------------ prune
def test_prune_forgets_old_settled_games_only():
    g, pl, clock, pid = setup()
    old = pl.start(TOKEN)["link"]["game"]
    pl.finish(TOKEN, old["id"])
    kept = pl.start(TOKEN)["link"]["game"]
    clock.t += SCRATCH_DAYS * 86400 + 1
    assert pl.prune() == 1
    assert g.store.park_link_game(pid, old["id"]) is None
    assert g.store.park_link_game(pid, kept["id"]) is not None


# ------------------------------------------------------------------------- HTTP
H = {"X-Player-Token": TOKEN}


@pytest.fixture()
def api(monkeypatch):
    g, pl, clock, pid = setup()
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:
        yield c, g, clock, pid


def test_http_flow(api):
    c, g, clock, pid = api
    assert c.get("/api/park/link").status_code == 401
    state = c.get("/api/park/link", headers=H).json()
    assert state["link"] == {"today": [], "played": 0, "levels": len(LEVELS), "game": None, "last": None}
    assert "park" in state and state["shards"] == SHARDS
    game = c.post("/api/park/link/start", json={}, headers=H).json()["link"]["game"]
    a, b = find_pair(game["board"], game["rows"], game["cols"])
    r = c.post("/api/park/link/move", json={"game": game["id"], "seq": 0, "a": a, "b": b}, headers=H)
    assert r.status_code == 200 and r.json() == {"seq": 1, "cleared": 1}
    r = c.post("/api/park/link/move", json={"game": game["id"], "seq": 5, "a": a, "b": b}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "bad_seq"
    r = c.post("/api/park/link/move", json={"game": game["id"], "seq": 1, "a": a, "b": b}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "bad_move"
    r = c.post("/api/park/link/move", json={"game": 999, "seq": 0, "a": a, "b": b}, headers=H)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_game"
    r = c.post("/api/park/link/finish", json={"game": game["id"]}, headers=H)
    assert r.status_code == 200 and r.json()["result"]["reason"] == "quit"
    for _ in LEVELS[1:]:
        gid = c.post("/api/park/link/start", headers=H).json()["link"]["game"]["id"]
        c.post("/api/park/link/finish", json={"game": gid}, headers=H)
    r = c.post("/api/park/link/start", headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "link_done"


def test_http_refusals_of_start(api):
    c, g, clock, pid = api
    g.store.update_player(pid, shards=0)
    r = c.post("/api/park/link/start", headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_shards"
    g.store.update_player(pid, taps_total=0)
    r = c.post("/api/park/link/start", headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "park_locked"


def test_http_account_required(api, monkeypatch):
    c, g, clock, pid = api
    monkeypatch.setattr(main, "accounts", object())
    monkeypatch.setitem(g.manifest.park["link"], "account", True)
    r = c.post("/api/park/link/start", headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "account_required"


def test_http_move_takes_the_claimed_time(api):
    c, g, clock, pid = api
    game = c.post("/api/park/link/start", headers=H).json()["link"]["game"]
    clock.t += 4
    a, b = find_pair(game["board"], game["rows"], game["cols"])
    for t in (-1, 86_400_001):
        r = c.post("/api/park/link/move", json={"game": game["id"], "seq": 0, "a": a, "b": b, "t": t}, headers=H)
        assert r.status_code == 422, t
    r = c.post("/api/park/link/move", json={"game": game["id"], "seq": 0, "a": a, "b": b, "t": 3000}, headers=H)
    assert r.json() == {"seq": 1, "cleared": 1}
    assert events(g, pid, game["id"])[0]["c"] == 3000


def test_http_game_ids_stay_in_sqlite_range(api):
    c, g, clock, pid = api
    for path, body in (("/api/park/link/move", {"seq": 0, "a": 0, "b": 1}), ("/api/park/link/finish", {})):
        for gid in (2**63, 0, -1):
            assert c.post(path, json={**body, "game": gid}, headers=H).status_code == 422, (path, gid)
        r = c.post(path, json={**body, "game": 2**63 - 1}, headers=H)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "no_game"


def test_http_without_the_link(monkeypatch):
    g = Game(Store(":memory:"), tiny_manifest(), now=Clock())
    monkeypatch.setattr(main, "game", g)
    r = TestClient(main.app).get("/api/park/link", headers=H)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_park"
