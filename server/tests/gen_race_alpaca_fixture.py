"""Writes client/src/panel/park/raceAlpaca.fixture.json: races run by the order rolled for every round and the alpaca,
as the server prepares and shows them (Races.prepare, then the race view for a 1.3.0 client), which
client/src/panel/park/race.test.ts and RaceTrack.test.ts play. Run from server/: PYTHONPATH=. .venv/bin/python
tests/gen_race_alpaca_fixture.py. The output depends only on the rules, the example economy's race and the deals and
seeds here; tests/test_race_alpaca.py checks the file is what they give (write it again when the example's race
changes)."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from app.game import Game
from app.manifest import Manifest
from app.park import Park
from app.park_race import Races, opened_at
from app.store import Store
from fixtures import Clock

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "client/src/panel/park/raceAlpaca.fixture.json"
ECONOMY = ROOT / "server/economy.example.json"
TOKEN = "race-fixture-token-000001"
# (dealer seed, race seed). Between them: the alpaca first in a round, last in one and first in the next (two drives
# before the same step), going back to the finish before a drive and home after one, drives over several squares with
# riders on, a rider stepping off, a group stepping onto its square, a drive in the slow last round, close-ups, and
# its die after the winning move, and rounds whose dice for the order are rolled again.
CASES = [(195, 19505), (283, 28305)]
# What a client plays a race from.
KEYS = ("id", "phase", "startsAt", "endsAt", "setup", "seed", "ranking", "leadMs", "rollMs", "stepMs", "slowFrom",
        "slowMs", "start", "moves", "rest", "cuts", "cutMs", "stepsMs", "pace", "order", "rolls", "orders", "drives",
        "orderRolls", "enter", "shuffleMs", "orderRollMs", "drivesMs", "drivePace", "enterMs", "replay")


def race_of(dealer: int, seed: int) -> dict[str, Any]:
    m = Manifest.load(economy=ECONOMY)
    cfg = m.park["race"]
    # The chances are left out of the fixture.
    cfg["sims"] = 10
    t0 = opened_at(cfg, 1_800_000_000)
    clock = Clock(t0 + 1)
    g = Game(Store(":memory:"), m, now=clock)
    races = Races(lambda: g, Park(lambda: g), dealer=random.Random(dealer), seeds=lambda: seed.to_bytes(32, "big"))
    g.status(TOKEN)
    races.tick()
    clock.t = t0 + cfg["betting"] + 1
    races.tick()
    r = races.view(TOKEN, "1.3.0")["race"]
    out = {k: r[k] for k in KEYS if k in r}
    out["setup"] = {k: v for k, v in r["setup"].items() if k != "chance"}
    return out


def build() -> list[dict[str, Any]]:
    return [race_of(d, s) for d, s in CASES]


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(build(), ensure_ascii=False) + "\n", encoding="utf-8")
