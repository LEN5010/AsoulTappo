"""The rows a lottery draw, a race settlement and a called-off race leave, the collection board's rows and the answers
of the park's actions, written out in full: how they are worked out may change, what they come to may not."""
import json

import test_race_park as rp
from app import park_race
from app.game import Game, board_id
from app.lottery import PRIZE, Lottery
from app.manifest import Manifest
from app.park import Park
from app.park_link import ParkLink
from app.park_scratch import ParkScratch
from app.store import Store, day_of
from fixtures import Clock
from test_lottery import Picks, at

TOKENS = [f"records-player-token-{i:04d}" for i in range(6)]


def _rows(g, labels, sql, *args):
    """The rows of [sql] as dicts, saves named by [labels] (p0, p1, ...) and JSON details parsed."""
    out = []
    for r in g.store._db.execute(sql, args).fetchall():
        d = dict(r)
        if "player_id" in d:
            d["player_id"] = labels.get(d["player_id"], d["player_id"])
        for key in ("detail", "result"):
            if isinstance(d.get(key), str):
                d[key] = json.loads(d[key])
        out.append(d)
    return out


def _lottery(*winning):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    park = Park(lambda: g, lambda nick: nick.replace("坏", "*"))
    lot = Lottery(lambda: g, park, pick=Picks(*winning))
    pids = []
    for token in TOKENS[:4]:
        pid = g.status(token)["player"]
        g.store.update_player(pid, coins=50, taps_total=10_000, gift_day=day_of(clock()))
        pids.append(pid)
    return g, lot, clock, pids


def _lottery_rows(g, pids, before, drawn):
    labels = {pid: f"p{i}" for i, pid in enumerate(pids)}
    now = g.now()
    return {
        "drawn": drawn,
        "tickets": _rows(g, labels, "SELECT id, day, player_id, number, tier, prize FROM lottery_tickets ORDER BY id"),
        "ledger": _rows(g, labels, "SELECT day, player_id, source, amount, count FROM shard_ledger WHERE source = ? "
                                   "ORDER BY player_id, day", PRIZE),
        "gained": {labels[p]: g.store.get_player(p, now)["shards"] - before[p] for p in pids},
        "counters": _rows(g, labels, "SELECT key, value FROM park_counters ORDER BY key"),
        "news": _rows(g, labels, "SELECT id, ts, kind, player_id, nick, detail FROM park_news ORDER BY id"),
        "days": _rows(g, labels, "SELECT day, number, drawn, result FROM lottery_days ORDER BY day"),
    }


def snapshot_lottery_with_winners():
    """Every tier won, two saves with top tickets (the earlier one named in the news), masked and default nicks."""
    g, lot, clock, pids = _lottery("123")
    g.store.update_player(pids[0], loadout='{"nick": "坏草"}')
    g.store.set_room_nick(pids[1], "房间里的坏名字")
    lot.buy(TOKENS[1], ["123"])
    lot.buy(TOKENS[0], ["123", "923", "003", "456"])
    lot.buy(TOKENS[2], ["123", "023", "023"])
    lot.buy(TOKENS[3], ["777"])
    before = {p: g.store.get_player(p, clock())["shards"] for p in pids}
    at(clock, g.manifest.park["lottery"]["drawAt"])
    return _lottery_rows(g, pids, before, lot.tick())


def snapshot_lottery_without_winners():
    """A day without a top or any winner, then a day without tickets."""
    g, lot, clock, pids = _lottery("123", "456")
    lot.buy(TOKENS[0], ["456", "780"])
    before = {p: g.store.get_player(p, clock())["shards"] for p in pids}
    draw_at = g.manifest.park["lottery"]["drawAt"]
    at(clock, draw_at)
    drawn = lot.tick()
    at(clock, draw_at, days=1)
    return _lottery_rows(g, pids, before, drawn + lot.tick())


def _race_rows(g, pids, extra):
    labels = {pid: f"p{i}" for i, pid in enumerate(pids)}
    now = g.now()
    return {
        **extra,
        "bets": _rows(g, labels, "SELECT id, race_id, player_id, kind, member, coins, odds, prize FROM park_race_bets "
                                 "ORDER BY id"),
        "coinLedger": _rows(g, labels, "SELECT day, player_id, source, amount, count FROM coin_ledger "
                                       "ORDER BY player_id, day, source"),
        "players": {labels[p]: {k: v for k, v in g.store.get_player(p, now).items()
                                if k in ("coins", "stamps_total", "shards")} for p in pids},
        "races": _rows(g, labels, "SELECT id, status FROM park_races ORDER BY id"),
        "counters": _rows(g, labels, "SELECT key, value FROM park_counters ORDER BY key"),
    }


def snapshot_race_settled():
    """Two saves, several winning and losing bets each, every win told to rooms (roomAt 1)."""
    g, races, clock, pid, other, ranking, before, wins = rp.settle_with_bets(roomAt=1)
    labels = {pid: "p0", other: "p1"}
    return _race_rows(g, [pid, other], {"ranking": ranking, "before": before,
                                        "wins": [{**w, "pid": labels[w["pid"]]} for w in wins]})


def snapshot_race_called_off():
    """Two saves whose bets passed stamp thresholds; the race never started."""
    g, races, clock, (pid, other) = rp.make()
    g.store.update_player(pid, coins=10, stamps_total=28)
    g.store.update_player(other, coins=9, stamps_total=27)
    races.tick()
    races.bet(rp.TOKEN, rp.T0, "win", rp.MEMBERS[0], 3)
    races.bet(rp.OTHER, rp.T0, "top2", rp.MEMBERS[2], 4)
    races.bet(rp.TOKEN, rp.T0, "last", rp.MEMBERS[4], 2)
    staked = _race_rows(g, [pid, other], {})
    clock.t = rp.T0 + rp.CFG["betting"] + park_race.START_GRACE + 1
    ticked = races.tick()
    return _race_rows(g, [pid, other], {"ticked": ticked, "staked": staked})


def snapshot_board():
    """Saves off the board by their own choice, however their loadout spells the key, saves with a nick that only
    reads like it, a photocard (which scores nothing), and the account-only board."""
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    pids = [g.status(t)["player"] for t in TOKENS]
    labels = {pid: f"p{i}" for i, pid in enumerate(pids)}
    # The six cards the rows were recorded with, named so that cards added later leave them as they are: five plain
    # ones and a 20-point one.
    cards = ["card:c1700742793002", "card:c1700742793004", "card:c1700742793005", "card:c1700742793007",
             "card:c1700742793008", "card:c1700742793010"]
    assert [g.board_points[i] for i in cards] == [2, 2, 2, 2, 2, 20]
    for i, pid in enumerate(pids):
        g.store.add_items(pid, {iid: 1 for iid in cards[:i + 1]}, clock())
    series = next(iter(g.manifest.photo_series))
    g.store.add_items(pids[0], {f"photo:{series}/x": 1, f"sign:{series}/x": 1}, clock())
    g.store.update_player(pids[1], loadout='{"board": false}')
    g.store.update_player(pids[2], loadout='{"\\u0062oard": false}')
    g.store.update_player(pids[3], loadout='{"nick": "board", "board": true}')
    g.store.update_player(pids[4], loadout='{"nick": "\\u5c0f\\u8349"}')
    g.store.set_room_nick(pids[5], "房间昵称")
    for i in (0, 2, 3):
        g.store.link_account(f"user-{i}", pids[i], clock())
    ids = {board_id(pid): labels[pid] for pid in pids}
    out = {}
    for require in (False, True):
        for order in ("cards", "score"):
            seen = [g.board(t, require, order) for t in TOKENS]
            rows = [{**r, "id": ids[r["id"]]} for r in seen[0]["cards"]]
            out[f"{order}{'/account' if require else ''}"] = {
                "rows": rows, "me": [b["me"] for b in seen],
                "total": seen[0]["total"], "points": seen[0]["points"]}
    return out


def test_a_lottery_draw_with_winners_leaves_these_rows():
    assert snapshot_lottery_with_winners() == LOTTERY_WITH_WINNERS


def test_a_lottery_draw_without_winners_leaves_these_rows():
    assert snapshot_lottery_without_winners() == LOTTERY_WITHOUT_WINNERS


def test_a_race_settlement_leaves_these_rows():
    assert snapshot_race_settled() == RACE_SETTLED


def test_a_called_off_race_leaves_these_rows():
    assert snapshot_race_called_off() == RACE_CALLED_OFF


def test_the_board_lists_these_rows():
    assert snapshot_board() == BOARD


# ------------------------------------------------------------------ answers
def _park():
    clock = Clock(rp.T0 + 1)
    g = Game(Store(":memory:"), rp.manifest(), now=clock)
    park = Park(lambda: g)
    return g, park, clock


def _status_and_park(g, park, token):
    return {**g.status(token), "park": park.state(token)}


def test_park_actions_answer_with_the_status_and_the_park_as_they_are_after_them():
    g, park, clock = _park()
    token = TOKENS[0]
    pid = g.status(token)["player"]
    g.store.update_player(pid, shards=100_000, taps_total=20_000)
    # The first status of the day gives the free coin; the answer carries the park after it.
    got = park.gift(token)
    assert got == {**_status_and_park(g, park, token), "gift": got["gift"]}
    assert park.buy(token, 30) == _status_and_park(g, park, token)

    lot = Lottery(lambda: g, park, pick=Picks("123"))
    got = lot.buy(token, ["123", "456"])
    with g.store.transaction() as st:
        lottery = lot.state_of(st, pid, g.now())
    assert got == {**_status_and_park(g, park, token), "lottery": lottery, "bought": got["bought"]}

    scratch = ParkScratch(park)
    got = scratch.buy(token, next(iter(g.manifest.park["scratch"]["cards"])))
    assert got == {**_status_and_park(g, park, token), **scratch.state(token)}

    link = ParkLink(park)
    got = link.state(token)
    assert got == {**_status_and_park(g, park, token), "link": link._view(g.store, pid, g.now())}


def test_a_bet_answers_with_the_race_as_it_is_after_the_bet():
    g, races, clock, (pid, other) = rp.make(coins=100)
    races.tick()
    races.bet(rp.OTHER, rp.T0, "win", rp.MEMBERS[1], 5)
    for kind, member, coins in (("win", rp.MEMBERS[0], 3), ("top2", rp.MEMBERS[0], 2), ("win", rp.MEMBERS[0], 4),
                                ("last", rp.MEMBERS[3], 1)):
        got = races.bet(rp.TOKEN, rp.T0, kind, member, coins)
        assert got == {**_status_and_park(g, races.park, rp.TOKEN),
                       "race": races._race(g.store.race_get(rp.T0), pid, g.now())}
        assert got["race"]["mine"][-1] == {"kind": kind, "member": member, "coins": coins,
                                           "odds": got["race"]["mine"][-1]["odds"]}

# ------------------------------------------------------------------ expected, as on pre-1.3.0 e8a1f96
LOTTERY_WITH_WINNERS = {'counters': [{'key': 'lottery_pool', 'value': 30000}, {'key': 'lottery_roll_second', 'value': 0}],
                        'days': [{'day': '2027-01-15',
                                  'drawn': 1800010500.0,
                                  'number': '123',
                                  'result': {'each': {'second': 5000, 'third': 600, 'top': 10150},
                                             'paid': 46050,
                                             'pool': 30000,
                                             'pools': {'second': 15000, 'top': 30450},
                                             'roll': {'second': 0},
                                             'sales': 9,
                                             'winners': {'second': 3, 'third': 1, 'top': 3}}},
                                 {'day': '2027-01-16', 'drawn': None, 'number': '999', 'result': {}}],
                        'drawn': ['2027-01-15'],
                        'gained': {'p0': 15750, 'p1': 10150, 'p2': 20150, 'p3': 0},
                        'ledger': [{'amount': 15750, 'count': 1, 'day': '2027-01-15', 'player_id': 'p0', 'source': 'lottery_prize'},
                                   {'amount': 10150, 'count': 1, 'day': '2027-01-15', 'player_id': 'p1', 'source': 'lottery_prize'},
                                   {'amount': 20150, 'count': 1, 'day': '2027-01-15', 'player_id': 'p2', 'source': 'lottery_prize'}],
                        'news': [{'detail': {'day': '2027-01-15',
                                             'each': {'second': 5000, 'third': 600, 'top': 10150},
                                             'nicks': ['房间里的*名字', '*草', '匿名小面包'],
                                             'number': '123',
                                             'winners': {'second': 3, 'third': 1, 'top': 3}},
                                  'id': 1,
                                  'kind': 'lottery_draw',
                                  'nick': '房间里的*名字',
                                  'player_id': 'p1',
                                  'ts': 1800010500.0}],
                        'tickets': [{'day': '2027-01-15', 'id': 1, 'number': '123', 'player_id': 'p1', 'prize': 10150, 'tier': 1},
                                    {'day': '2027-01-15', 'id': 2, 'number': '123', 'player_id': 'p0', 'prize': 10150, 'tier': 1},
                                    {'day': '2027-01-15', 'id': 3, 'number': '923', 'player_id': 'p0', 'prize': 5000, 'tier': 2},
                                    {'day': '2027-01-15', 'id': 4, 'number': '003', 'player_id': 'p0', 'prize': 600, 'tier': 3},
                                    {'day': '2027-01-15', 'id': 5, 'number': '456', 'player_id': 'p0', 'prize': 0, 'tier': 0},
                                    {'day': '2027-01-15', 'id': 6, 'number': '123', 'player_id': 'p2', 'prize': 10150, 'tier': 1},
                                    {'day': '2027-01-15', 'id': 7, 'number': '023', 'player_id': 'p2', 'prize': 5000, 'tier': 2},
                                    {'day': '2027-01-15', 'id': 8, 'number': '023', 'player_id': 'p2', 'prize': 5000, 'tier': 2},
                                    {'day': '2027-01-15', 'id': 9, 'number': '777', 'player_id': 'p3', 'prize': 0, 'tier': 0}]}
LOTTERY_WITHOUT_WINNERS = {'counters': [{'key': 'lottery_pool', 'value': 30100}, {'key': 'lottery_roll_second', 'value': 0}],
                           'days': [{'day': '2027-01-15',
                                     'drawn': 1800010500.0,
                                     'number': '123',
                                     'result': {'each': {'second': 0, 'third': 0, 'top': 0},
                                                'paid': 0,
                                                'pool': 30100,
                                                'pools': {'second': 0, 'top': 30100},
                                                'roll': {'second': 0},
                                                'sales': 2,
                                                'winners': {'second': 0, 'third': 0, 'top': 0}}},
                                    {'day': '2027-01-16',
                                     'drawn': 1800096900.0,
                                     'number': '456',
                                     'result': {'each': {'second': 0, 'third': 0, 'top': 0},
                                                'paid': 0,
                                                'pool': 30100,
                                                'pools': {'second': 0, 'top': 30100},
                                                'roll': {'second': 0},
                                                'sales': 0,
                                                'winners': {'second': 0, 'third': 0, 'top': 0}}},
                                    {'day': '2027-01-17', 'drawn': None, 'number': '999', 'result': {}}],
                           'drawn': ['2027-01-15', '2027-01-16'],
                           'gained': {'p0': 0, 'p1': 0, 'p2': 0, 'p3': 0},
                           'ledger': [],
                           'news': [{'detail': {'day': '2027-01-15',
                                                'each': {'second': 0, 'third': 0, 'top': 0},
                                                'nicks': [],
                                                'number': '123',
                                                'winners': {'second': 0, 'third': 0, 'top': 0}},
                                     'id': 1,
                                     'kind': 'lottery_draw',
                                     'nick': '',
                                     'player_id': '',
                                     'ts': 1800010500.0}],
                           'tickets': [{'day': '2027-01-15', 'id': 1, 'number': '456', 'player_id': 'p0', 'prize': 0, 'tier': 0},
                                       {'day': '2027-01-15', 'id': 2, 'number': '780', 'player_id': 'p0', 'prize': 0, 'tier': 0}]}
RACE_SETTLED = {'before': 43,
                'bets': [{'coins': 2,
                          'id': 1,
                          'kind': 'win',
                          'member': 'sinuo',
                          'odds': 42,
                          'player_id': 'p0',
                          'prize': 84,
                          'race_id': 1799925000},
                         {'coins': 1,
                          'id': 2,
                          'kind': 'top2',
                          'member': 'beila',
                          'odds': 21,
                          'player_id': 'p0',
                          'prize': 21,
                          'race_id': 1799925000},
                         {'coins': 3,
                          'id': 3,
                          'kind': 'last',
                          'member': 'sinuo',
                          'odds': 42,
                          'player_id': 'p0',
                          'prize': 0,
                          'race_id': 1799925000},
                         {'coins': 4,
                          'id': 4,
                          'kind': 'win',
                          'member': 'sinuo',
                          'odds': 39,
                          'player_id': 'p1',
                          'prize': 156,
                          'race_id': 1799925000},
                         {'coins': 1,
                          'id': 5,
                          'kind': 'win',
                          'member': 'jiaran',
                          'odds': 45,
                          'player_id': 'p1',
                          'prize': 0,
                          'race_id': 1799925000},
                         {'coins': 1,
                          'id': 6,
                          'kind': 'win',
                          'member': 'sinuo',
                          'odds': 34,
                          'player_id': 'p0',
                          'prize': 34,
                          'race_id': 1799925000}],
                'coinLedger': [{'amount': -5, 'count': 2, 'day': '2027-01-14', 'player_id': 'p1', 'source': 'race'},
                               {'amount': 16, 'count': 1, 'day': '2027-01-15', 'player_id': 'p1', 'source': 'race_prize'},
                               {'amount': -7, 'count': 4, 'day': '2027-01-14', 'player_id': 'p0', 'source': 'race'},
                               {'amount': 14, 'count': 1, 'day': '2027-01-15', 'player_id': 'p0', 'source': 'race_prize'}],
                'counters': [{'key': 'lottery_pool', 'value': 30600}],
                'players': {'p0': {'coins': 57, 'shards': 1600, 'stamps_total': 7},
                            'p1': {'coins': 61, 'shards': 1600, 'stamps_total': 5}},
                'races': [{'id': 1799925000, 'status': 'settled'}, {'id': 1800011400, 'status': 'open'}],
                'ranking': ['sinuo', 'beila', 'nailin', 'xinyi', 'jiaran'],
                'wins': [{'coins': 14, 'pid': 'p0'}, {'coins': 16, 'pid': 'p1'}]}
RACE_CALLED_OFF = {'bets': [{'coins': 3,
                             'id': 1,
                             'kind': 'win',
                             'member': 'jiaran',
                             'odds': 42,
                             'player_id': 'p0',
                             'prize': 0,
                             'race_id': 1799925000},
                            {'coins': 4,
                             'id': 2,
                             'kind': 'top2',
                             'member': 'beila',
                             'odds': 21,
                             'player_id': 'p1',
                             'prize': 0,
                             'race_id': 1799925000},
                            {'coins': 2,
                             'id': 3,
                             'kind': 'last',
                             'member': 'sinuo',
                             'odds': 42,
                             'player_id': 'p0',
                             'prize': 0,
                             'race_id': 1799925000}],
                   'coinLedger': [{'amount': -4, 'count': 1, 'day': '2027-01-14', 'player_id': 'p1', 'source': 'race'},
                                  {'amount': 1, 'count': 1, 'day': '2027-01-14', 'player_id': 'p1', 'source': 'stamp'},
                                  {'amount': 4, 'count': 1, 'day': '2027-01-15', 'player_id': 'p1', 'source': 'race_refund'},
                                  {'amount': -1, 'count': 0, 'day': '2027-01-15', 'player_id': 'p1', 'source': 'stamp'},
                                  {'amount': -5, 'count': 2, 'day': '2027-01-14', 'player_id': 'p0', 'source': 'race'},
                                  {'amount': 1, 'count': 1, 'day': '2027-01-14', 'player_id': 'p0', 'source': 'stamp'},
                                  {'amount': 5, 'count': 1, 'day': '2027-01-15', 'player_id': 'p0', 'source': 'race_refund'},
                                  {'amount': -1, 'count': 0, 'day': '2027-01-15', 'player_id': 'p0', 'source': 'stamp'}],
                   'counters': [{'key': 'lottery_pool', 'value': 30000}],
                   'players': {'p0': {'coins': 10, 'shards': 1600, 'stamps_total': 28},
                               'p1': {'coins': 9, 'shards': 1600, 'stamps_total': 27}},
                   'races': [{'id': 1799925000, 'status': 'void'}, {'id': 1800011400, 'status': 'open'}],
                   'staked': {'bets': [{'coins': 3,
                                        'id': 1,
                                        'kind': 'win',
                                        'member': 'jiaran',
                                        'odds': 42,
                                        'player_id': 'p0',
                                        'prize': 0,
                                        'race_id': 1799925000},
                                       {'coins': 4,
                                        'id': 2,
                                        'kind': 'top2',
                                        'member': 'beila',
                                        'odds': 21,
                                        'player_id': 'p1',
                                        'prize': 0,
                                        'race_id': 1799925000},
                                       {'coins': 2,
                                        'id': 3,
                                        'kind': 'last',
                                        'member': 'sinuo',
                                        'odds': 42,
                                        'player_id': 'p0',
                                        'prize': 0,
                                        'race_id': 1799925000}],
                              'coinLedger': [{'amount': -4, 'count': 1, 'day': '2027-01-14', 'player_id': 'p1', 'source': 'race'},
                                             {'amount': 1, 'count': 1, 'day': '2027-01-14', 'player_id': 'p1', 'source': 'stamp'},
                                             {'amount': -5, 'count': 2, 'day': '2027-01-14', 'player_id': 'p0', 'source': 'race'},
                                             {'amount': 1, 'count': 1, 'day': '2027-01-14', 'player_id': 'p0', 'source': 'stamp'}],
                              'counters': [{'key': 'lottery_pool', 'value': 30450}],
                              'players': {'p0': {'coins': 6, 'shards': 1600, 'stamps_total': 33},
                                          'p1': {'coins': 6, 'shards': 1600, 'stamps_total': 31}},
                              'races': [{'id': 1799925000, 'status': 'open'}, {'id': 1800011400, 'status': 'open'}]},
                   'ticked': []}
# The board's total is every card of the manifest.
CARD_COUNT = len(Manifest.load().cards)
BOARD = {'cards': {'me': [{'big': 0, 'cards': 1, 'off': None, 'rank': 4, 'score': 2, 'skins': 0},
                          {'big': 0, 'cards': 2, 'off': 'hidden', 'rank': None, 'score': 4, 'skins': 0},
                          {'big': 0, 'cards': 3, 'off': 'hidden', 'rank': None, 'score': 6, 'skins': 0},
                          {'big': 0, 'cards': 4, 'off': None, 'rank': 3, 'score': 8, 'skins': 0},
                          {'big': 0, 'cards': 5, 'off': None, 'rank': 2, 'score': 10, 'skins': 0},
                          {'big': 0, 'cards': 6, 'off': None, 'rank': 1, 'score': 30, 'skins': 0}],
                   'points': {'big': 300,
                              'card': 2,
                              'emote': 1,
                              'emoteRare': 3,
                              'emoteScratch': 3,
                              'emoteUncommon': 2,
                              'epic': 20,
                              'holo': 20,
                              'limited': 20,
                              'skin': 150},
                   'rows': [{'big': 0,
                             'cards': 6,
                             'character': '',
                             'id': 'p5',
                             'nick': '房间昵称',
                             'plate': None,
                             'rank': 1,
                             'score': 30,
                             'skins': 0},
                            {'big': 0,
                             'cards': 5,
                             'character': '',
                             'id': 'p4',
                             'nick': '小草',
                             'plate': None,
                             'rank': 2,
                             'score': 10,
                             'skins': 0},
                            {'big': 0,
                             'cards': 4,
                             'character': '',
                             'id': 'p3',
                             'nick': 'board',
                             'plate': None,
                             'rank': 3,
                             'score': 8,
                             'skins': 0},
                            {'big': 0,
                             'cards': 1,
                             'character': '',
                             'id': 'p0',
                             'nick': '匿名小面包',
                             'plate': None,
                             'rank': 4,
                             'score': 2,
                             'skins': 0}],
                   'total': CARD_COUNT},
         'cards/account': {'me': [{'big': 0, 'cards': 1, 'off': None, 'rank': 2, 'score': 2, 'skins': 0},
                                  {'big': 0, 'cards': 2, 'off': 'hidden', 'rank': None, 'score': 4, 'skins': 0},
                                  {'big': 0, 'cards': 3, 'off': 'hidden', 'rank': None, 'score': 6, 'skins': 0},
                                  {'big': 0, 'cards': 4, 'off': None, 'rank': 1, 'score': 8, 'skins': 0},
                                  {'big': 0, 'cards': 5, 'off': 'account', 'rank': None, 'score': 10, 'skins': 0},
                                  {'big': 0, 'cards': 6, 'off': 'account', 'rank': None, 'score': 30, 'skins': 0}],
                           'points': {'big': 300,
                                      'card': 2,
                                      'emote': 1,
                                      'emoteRare': 3,
                                      'emoteScratch': 3,
                                      'emoteUncommon': 2,
                                      'epic': 20,
                                      'holo': 20,
                                      'limited': 20,
                                      'skin': 150},
                           'rows': [{'big': 0,
                                     'cards': 4,
                                     'character': '',
                                     'id': 'p3',
                                     'nick': 'board',
                                     'plate': None,
                                     'rank': 1,
                                     'score': 8,
                                     'skins': 0},
                                    {'big': 0,
                                     'cards': 1,
                                     'character': '',
                                     'id': 'p0',
                                     'nick': '匿名小面包',
                                     'plate': None,
                                     'rank': 2,
                                     'score': 2,
                                     'skins': 0}],
                           'total': CARD_COUNT},
         'score': {'me': [{'big': 0, 'cards': 1, 'off': None, 'rank': 4, 'score': 2, 'skins': 0},
                          {'big': 0, 'cards': 2, 'off': 'hidden', 'rank': None, 'score': 4, 'skins': 0},
                          {'big': 0, 'cards': 3, 'off': 'hidden', 'rank': None, 'score': 6, 'skins': 0},
                          {'big': 0, 'cards': 4, 'off': None, 'rank': 3, 'score': 8, 'skins': 0},
                          {'big': 0, 'cards': 5, 'off': None, 'rank': 2, 'score': 10, 'skins': 0},
                          {'big': 0, 'cards': 6, 'off': None, 'rank': 1, 'score': 30, 'skins': 0}],
                   'points': {'big': 300,
                              'card': 2,
                              'emote': 1,
                              'emoteRare': 3,
                              'emoteScratch': 3,
                              'emoteUncommon': 2,
                              'epic': 20,
                              'holo': 20,
                              'limited': 20,
                              'skin': 150},
                   'rows': [{'big': 0,
                             'cards': 6,
                             'character': '',
                             'id': 'p5',
                             'nick': '房间昵称',
                             'plate': None,
                             'rank': 1,
                             'score': 30,
                             'skins': 0},
                            {'big': 0,
                             'cards': 5,
                             'character': '',
                             'id': 'p4',
                             'nick': '小草',
                             'plate': None,
                             'rank': 2,
                             'score': 10,
                             'skins': 0},
                            {'big': 0,
                             'cards': 4,
                             'character': '',
                             'id': 'p3',
                             'nick': 'board',
                             'plate': None,
                             'rank': 3,
                             'score': 8,
                             'skins': 0},
                            {'big': 0,
                             'cards': 1,
                             'character': '',
                             'id': 'p0',
                             'nick': '匿名小面包',
                             'plate': None,
                             'rank': 4,
                             'score': 2,
                             'skins': 0}],
                   'total': CARD_COUNT},
         'score/account': {'me': [{'big': 0, 'cards': 1, 'off': None, 'rank': 2, 'score': 2, 'skins': 0},
                                  {'big': 0, 'cards': 2, 'off': 'hidden', 'rank': None, 'score': 4, 'skins': 0},
                                  {'big': 0, 'cards': 3, 'off': 'hidden', 'rank': None, 'score': 6, 'skins': 0},
                                  {'big': 0, 'cards': 4, 'off': None, 'rank': 1, 'score': 8, 'skins': 0},
                                  {'big': 0, 'cards': 5, 'off': 'account', 'rank': None, 'score': 10, 'skins': 0},
                                  {'big': 0, 'cards': 6, 'off': 'account', 'rank': None, 'score': 30, 'skins': 0}],
                           'points': {'big': 300,
                                      'card': 2,
                                      'emote': 1,
                                      'emoteRare': 3,
                                      'emoteScratch': 3,
                                      'emoteUncommon': 2,
                                      'epic': 20,
                                      'holo': 20,
                                      'limited': 20,
                                      'skin': 150},
                           'rows': [{'big': 0,
                                     'cards': 4,
                                     'character': '',
                                     'id': 'p3',
                                     'nick': 'board',
                                     'plate': None,
                                     'rank': 1,
                                     'score': 8,
                                     'skins': 0},
                                    {'big': 0,
                                     'cards': 1,
                                     'character': '',
                                     'id': 'p0',
                                     'nick': '匿名小面包',
                                     'plate': None,
                                     'rank': 2,
                                     'score': 2,
                                     'skins': 0}],
                           'total': CARD_COUNT}}
