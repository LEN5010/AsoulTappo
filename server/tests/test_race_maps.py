"""The dumpling race on a map and with skills (app/race.py), and what a client from before them is given
(app/park_race.py)."""
import random

import pytest

from app import park_race, race
from app.game import Game
from app.manifest import Manifest
from app.park import Park
from app.park_race import Races
from app.store import Store
from fixtures import Clock
from test_race import FIRST, KEEP, Script
from test_race_park import T0, TOKEN, seeds

M = Manifest.load()
CFG = M.park["race"]
MEMBERS = tuple(c["id"] for c in M.data["characters"])
J, N, B, X, S = MEMBERS
DICE = (1, 2, 3)
OPEN = KEEP + FIRST


def die(n):
    return DICE.index(n)


def rules(squares=(), track=24):
    cfg = {**CFG, "dice": list(DICE), "maps": [{"id": "t", "track": track, "squares": list(squares)}], "skills": []}
    return race.Rules.of(cfg, MEMBERS)


def setup(r, **skills):
    """The rules' one map, and the skills named by member."""
    return {"map": r.maps[0], "skills": skills}


def run(r, su, *belows):
    return race.run(r, su, Script(OPEN + list(belows)))


def replay(out):
    """The final ranking rebuilt from the lanes and the move list alone, as a client does: the mover and those it
    carries leave their square, land on `end` (or `to`), a flip square turns its stack, and `stack` is the square
    as it is once someone climbed."""
    lane = {m: i for i, m in enumerate(out["start"])}
    pos = dict.fromkeys(out["start"], 0)
    stacks = {}
    for step in out["moves"]:
        group = [step["m"], *step.get("carry", [])]
        if step["from"]:
            assert all(m in stacks[step["from"]] for m in group)
            stacks[step["from"]] = [m for m in stacks[step["from"]] if m not in group]
        q = step.get("end", step["to"])
        if q:
            stacks.setdefault(q, []).extend(group)
        if step.get("square") == "flip":
            stacks[q].reverse()
        if "stack" in step:
            assert sorted(step["stack"]) == sorted(stacks[q])
            stacks[q] = list(step["stack"])
        for m in group:
            pos[m] = q
    return sorted(pos, key=lambda m: (pos[m], stacks[pos[m]].index(m) if pos[m] else -lane[m]), reverse=True)


# ---------------------------------------------------------------- maps
def test_a_race_is_run_on_one_of_the_maps_copied_into_its_setup():
    r = race.Rules.of(CFG, MEMBERS)
    assert len(r.maps) == len(CFG["maps"]) > 1
    seen = {race.deal(r, random.Random(i))["map"]["id"] for i in range(60)}
    assert seen == {m["id"] for m in CFG["maps"]}
    su = race.deal(r, random.Random(1))
    assert set(su) == {"map"} and race.track_of(r, su) == su["map"]["track"]
    # A setup from before maps is run on the manifest's lap.
    assert race.track_of(r, {"boost": 5, "trip": 6}) == CFG["track"]


@pytest.mark.parametrize("bad", [
    {"track": 13},
    {"track": 12},
    {"squares": [{"at": 3, "kind": "swamp"}]},
    {"squares": [{"at": 0, "kind": "flip"}]},
    {"squares": [{"at": 24, "kind": "flip"}]},
    {"squares": [{"at": 3, "kind": "flip"}, {"at": 3, "kind": "again"}]},
    {"squares": [{"at": 3, "kind": "boost", "by": 0}]},
    {"squares": [{"at": 3, "kind": "trip"}]},
    {"squares": [{"at": 9, "kind": "portal", "to": 9}]},
    {"squares": [{"at": 9, "kind": "portal", "to": 12}, {"at": 12, "kind": "flip"}]},
    {"id": ""},
])
def test_a_map_the_race_could_not_be_run_on_is_refused(bad):
    with pytest.raises((ValueError, KeyError)):
        race.read_map({"id": "t", "track": 24, "squares": [], **bad})


@pytest.mark.parametrize("bad", [
    {"id": "fly", "dice": [1, 2]},
    {"id": "burst", "dice": [1, 2]},
    {"id": "burst", "dice": [1, 2], "chance": 0},
    {"id": "steady", "dice": []},
    {"id": "chase", "dice": [1, 2], "by": 0},
])
def test_a_skill_the_race_could_not_deal_is_refused(bad):
    with pytest.raises((ValueError, KeyError)):
        race.read_skill(bad)


def test_boost_and_trip_squares_move_by_their_own_number():
    r = rules([{"at": 3, "kind": "boost", "by": 4}, {"at": 2, "kind": "trip", "by": 2}])
    out = run(r, setup(r), die(3), die(2))
    assert out["moves"][0] == {"m": J, "dice": [3], "steps": 3, "from": 0, "to": 3, "square": "boost", "end": 7}
    # Back to the start line: nobody is stacked there.
    assert out["moves"][1] == {"m": N, "dice": [2], "steps": 2, "from": 0, "to": 2, "square": "trip", "end": 0}


def test_the_again_square_rolls_the_die_once_more():
    r = rules([{"at": 3, "kind": "again"}, {"at": 5, "kind": "boost", "by": 2}])
    out = run(r, setup(r), die(3), die(2))
    # The second walk ends on the boost square, which does nothing: a square acts on the die's own landing only.
    assert out["moves"][0] == {"m": J, "dice": [3, 2], "steps": 3, "from": 0, "to": 3, "square": "again", "end": 5}


def test_the_hook_square_pulls_onto_the_nearest_dumplings_ahead():
    r = rules([{"at": 1, "kind": "hook"}])
    out = run(r, setup(r), die(1), die(3), die(1), die(2), die(1))
    # Nobody ahead yet: it stays.
    assert out["moves"][0] == {"m": J, "dice": [1], "steps": 1, "from": 0, "to": 1, "square": "hook", "end": 1}
    assert out["moves"][2] == {"m": B, "dice": [1], "steps": 1, "from": 0, "to": 1, "square": "hook", "end": 3}
    # The nearest of two squares ahead.
    assert out["moves"][4]["end"] == 2


# ---------------------------------------------------------------- skills
def test_a_burst_walks_its_die_twice_on_its_chance():
    r = rules()
    out = run(r, setup(r, **{J: {"id": "burst", "chance": 25}}), die(2), 24, die(1), die(1), die(1), die(1), die(2), 25)
    assert out["moves"][0] == {"m": J, "dice": [2], "steps": 4, "from": 0, "to": 4, "skill": "burst"}
    assert out["moves"][5] == {"m": J, "dice": [2], "steps": 2, "from": 4, "to": 6}


def test_a_chase_walks_further_while_it_is_last():
    r = rules()
    out = run(r, setup(r, **{S: {"id": "chase", "by": 2}}), die(3), die(3), die(3), die(3), die(1),
              die(1), die(1), die(1), die(1), die(1))
    # The bottom lane, still on the start line when its turn comes.
    assert out["moves"][4] == {"m": S, "dice": [1], "steps": 3, "from": 0, "to": 3, "skill": "chase"}
    # On top of the others now, and carried along: no longer last.
    assert out["moves"][9]["m"] == S and "skill" not in out["moves"][9] and out["moves"][9]["steps"] == 1


def test_a_porter_walks_further_with_others_on_its_head():
    r = rules()
    out = run(r, setup(r, **{J: {"id": "porter", "by": 2}}), die(1), die(1), die(3), die(3), die(3), die(1))
    assert "skill" not in out["moves"][0]
    assert out["moves"][5] == {"m": J, "dice": [1], "steps": 3, "from": 1, "to": 4, "carry": [N], "skill": "porter"}


def test_a_solo_leaves_its_riders_behind_on_its_chance():
    r = rules()
    out = run(r, setup(r, **{J: {"id": "solo", "chance": 50, "by": 1}}), die(1), die(1), die(1), die(3), die(3),
              die(1), 49, die(1))
    assert out["moves"][5] == {"m": J, "dice": [1], "steps": 3, "from": 1, "to": 4, "skill": "solo", "left": [N, B]}
    # Those left keep their order on the square.
    assert out["moves"][6] == {"m": N, "dice": [1], "steps": 1, "from": 1, "to": 2, "carry": [B]}
    out = run(r, setup(r, **{J: {"id": "solo", "chance": 50, "by": 1}}), die(1), die(1), die(1), die(3), die(3),
              die(1), 50)
    assert out["moves"][5] == {"m": J, "dice": [1], "steps": 1, "from": 1, "to": 2, "carry": [N, B]}


def test_a_dash_ends_on_the_finish_it_would_pass():
    r = race.Rules(members=MEMBERS, track=4, dice=DICE, square_range=(10, 11), boost=2, trip=-1)
    su = {"boost": 10, "trip": 11, "skills": {J: {"id": "dash"}}}
    out = race.run(r, su, Script(OPEN + [die(3), die(1), die(1), die(1), die(1), die(3)]))
    assert out["moves"][-1] == {"m": J, "dice": [3], "steps": 3, "from": 3, "to": 4, "skill": "dash"}
    assert out["ranking"][0] == J
    # Without it the same die walks back from the finish.
    out = race.run(r, {"boost": 10, "trip": 11}, Script(OPEN + [die(3), die(1), die(1), die(1), die(1), die(3)]))
    assert out["moves"][5]["to"] == 2


def test_a_shield_is_not_set_back():
    r = rules([{"at": 2, "kind": "trip", "by": 1}, {"at": 1, "kind": "portal", "to": 3}])
    su = setup(r, **{J: {"id": "shield"}, N: {"id": "shield"}, X: {"id": "shield"}})
    out = run(r, su, die(2), die(3), die(2), die(1))
    assert out["moves"][0] == {"m": J, "dice": [2], "steps": 2, "from": 0, "to": 2, "skill": "shield"}
    # The far end of the portal would take it back.
    assert out["moves"][1] == {"m": N, "dice": [3], "steps": 3, "from": 0, "to": 3, "skill": "shield"}
    assert out["moves"][2] == {"m": B, "dice": [2], "steps": 2, "from": 0, "to": 2, "square": "trip", "end": 1}
    # The near end takes it on, shield or not.
    assert out["moves"][3] == {"m": X, "dice": [1], "steps": 1, "from": 0, "to": 1, "square": "portal", "end": 3}


def test_a_climber_goes_to_the_top_when_others_land_on_it():
    r = rules()
    out = run(r, setup(r, **{J: {"id": "climb"}}), die(2), die(2), die(1))
    assert out["moves"][1] == {"m": N, "dice": [2], "steps": 2, "from": 0, "to": 2, "react": [J], "stack": [N, J]}
    assert "react" not in out["moves"][0] and "react" not in out["moves"][2]


def test_skills_are_dealt_one_each_with_their_dice():
    r = race.Rules.of(CFG, MEMBERS)
    dealt = race.deal_skills(r, random.Random(5))
    ids = [k["id"] for k in dealt["skills"].values()]
    assert set(dealt["skills"]) == set(MEMBERS) == set(dealt["dice"]) and len(set(ids)) == len(MEMBERS)
    by_id = {k["id"]: k for k in CFG["skills"]}
    for m in MEMBERS:
        k = dealt["skills"][m]
        assert dealt["dice"][m] == by_id[k["id"]]["dice"] and "dice" not in k
        assert {key: by_id[k["id"]][key] for key in k} == k
    assert race.deal_skills(rules(), random.Random(5)) is None


def test_the_moves_alone_rebuild_every_race():
    r = race.Rules.of(CFG, MEMBERS)
    dealer = random.Random(11)
    seen = set()
    for i in range(400):
        su = {**race.deal(r, dealer), **race.deal_skills(r, dealer)}
        out = race.run(r, su, race.SimRng(i))
        assert replay(out) == out["ranking"]
        track = su["map"]["track"]
        assert out["moves"][-1].get("end", out["moves"][-1]["to"]) == track
        for step in out["moves"]:
            seen.update(v for k, v in step.items() if k in ("square", "skill"))
            seen.update("climb" for _ in step.get("react", ()))
    # Every square and every skill that shows in a move has been played.
    assert seen == set(race.SQUARE_KINDS) | set(race.SKILLS) - {"steady"}


def test_a_seed_still_decides_the_whole_race():
    r = race.Rules.of(CFG, MEMBERS)
    dealer = random.Random(2)
    su = {**race.deal(r, dealer), **race.deal_skills(r, dealer)}
    assert race.run_seed(r, su, b"seed") == race.run_seed(r, su, b"seed")


# ---------------------------------------------------------------- the schedule
def make():
    m = Manifest.load()
    m.park["race"]["sims"] = 300
    clock = Clock(T0 + 1)
    g = Game(Store(":memory:"), m, now=clock)
    races = Races(lambda: g, Park(lambda: g), dealer=random.Random(3), seeds=seeds())
    g.status(TOKEN)
    return races, clock


def test_a_race_is_prepared_with_a_map_skills_and_their_chances():
    races, clock = make()
    races.tick()
    su = races.view(TOKEN, "1.2.5")["race"]["setup"]
    assert set(su) == {"map", "skills", "dice", "chance"} and su["chance"]["sims"] == 300
    assert su["map"]["id"] in {m["id"] for m in CFG["maps"]}


@pytest.mark.parametrize("version, plays", [("1.2.5", True), ("1.2.5-rc.1", True), ("1.3.0", True), ("1.2.4", False),
                                             ("", False), (None, False)])
def test_a_client_from_before_maps_gets_the_result_without_the_moves(version, plays):
    assert park_race.plays_maps(version) is plays
    races, clock = make()
    races.tick()
    clock.t = T0 + CFG["betting"] + 1
    races.tick()
    r = races.view(TOKEN, version)["race"]
    assert r["phase"] == "running" and r["replay"] is plays and ("moves" in r) is plays and len(r["ranking"]) == 5
    clock.t = r["endsAt"] + 1
    races.tick()
    past = races.history(TOKEN, version)["races"][0]
    assert past["replay"] is plays
    if plays:
        assert races.replay(TOKEN, past["id"], version)["race"]["moves"]
    else:
        with pytest.raises(Exception) as e:
            races.replay(TOKEN, past["id"], version)
        assert e.value.code == "no_replay"


def test_a_race_with_skills_names_its_close_ups_and_lasts_as_long_as_they_take():
    seen = 0
    for k in range(6):
        races, clock = make()
        clock.t = T0 + k * CFG["interval"]
        races.tick()
        clock.t += CFG["betting"] + 1
        races.tick()
        r = races.view(TOKEN, "1.2.5")["race"]
        cuts = r.get("cuts", [])
        assert cuts == park_race.cuts_of(r["moves"])
        # Once a member at most, each at a step where that member's skill is at work.
        assert len({c["m"] for c in cuts}) == len(cuts) <= 5
        for c in cuts:
            move = r["moves"][c["at"]]
            assert (move["m"] == c["m"] and move.get("skill")) or c["m"] in move.get("react", [])
        if cuts:
            seen += 1
            assert r["cutMs"] == park_race.cut_ms(r["stepMs"])
        else:
            assert "cutMs" not in r
        assert r["endsAt"] == r["startsAt"] + park_race.playback_ms(
            r["leadMs"], len(r["moves"]), r["stepMs"], r["slowMs"], cuts=len(cuts)) / 1000
    assert seen


# ---------------------------------------------------------------- a map's route across the board
def route_map(runs, track, start=(0, 0), **more):
    return {"id": "t", "track": track, "path": {"from": list(start), "runs": runs}, **more}


def test_a_route_gives_every_square_from_the_start_to_the_finish_its_cell():
    m = race.read_map(route_map("R8 U2 L8 U2 R6", 26, start=(0, 4)))
    assert len(m["path"]) == 27
    assert m["path"][0] == [0, 4] and m["path"][8] == [8, 4] and m["path"][10] == [8, 2] and m["path"][-1] == [6, 0]
    # A lap has no route, and its track is even; a route may be odd.
    assert "path" not in race.read_map({"id": "t", "track": 24})
    assert race.read_map(route_map("R15", 15))["track"] == 15
    with pytest.raises(ValueError):
        race.read_map({"id": "t", "track": 15})


@pytest.mark.parametrize("runs,track,start", [
    ("R8 U2 L8", 20, (0, 4)),        # two squares short of the track
    ("R16", 16, (0, 0)),             # off the board's right edge
    ("L3 D12", 15, (3, 0)),          # off its foot
    ("R4 D2 L2 U4 R12", 24, (0, 2)), # crosses itself
    ("R8 D1 L8 D6", 23, (0, 0)),     # two rows side by side: the way cannot be read
    ("R8 X2 L8", 18, (0, 0)),        # not a run
    ("R8 U0 R8", 16, (0, 0)),        # a run of no squares
])
def test_a_route_the_board_cannot_show_is_refused(runs, track, start):
    with pytest.raises(ValueError):
        race.read_map(route_map(runs, track, start))


def test_the_manifests_routes_fit_their_tracks_and_change_nothing_of_the_race():
    routed = [m for m in CFG["maps"] if m.get("path") and m["track"] % 2 == 0]
    assert routed
    for raw in routed:
        on = race.Rules.of({**CFG, "maps": [raw]}, MEMBERS)
        off = race.Rules.of({**CFG, "maps": [{k: v for k, v in raw.items() if k != "path"}]}, MEMBERS)
        assert len(on.maps[0]["path"]) == raw["track"] + 1 and "path" not in off.maps[0]
        for n in range(10):
            dealt = [{**race.deal(r, d), **(race.deal_skills(r, d) or {})} for r, d in ((on, random.Random(n)), (off, random.Random(n)))]
            # The setup carries the route, so the board can be drawn from the race alone.
            assert dealt[0]["map"]["path"] == on.maps[0]["path"]
            assert race.run(on, dealt[0], race.SimRng(n))["moves"] == race.run(off, dealt[1], race.SimRng(n))["moves"]
