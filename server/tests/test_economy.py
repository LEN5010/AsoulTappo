"""The economy file: kept apart from the manifest, its server-only part never reaches a client."""
import json
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import economy
from app.cards import DropConfig
from app.manifest import Manifest


def test_the_server_needs_the_economy_file(monkeypatch):
    monkeypatch.delenv(economy.ENV, raising=False)
    with pytest.raises(RuntimeError, match=economy.ENV):
        Manifest.load()


def test_anti_cheat_settings_stay_on_the_server():
    data, anti = economy.load(economy.EXAMPLE)
    assert economy.SERVER_ONLY not in data and not any(k.startswith("_") for k in data)
    assert economy.drop_config(anti) == DropConfig(**anti)
    client = TestClient(main.app)
    for path in ("/api/economy", "/api/manifest"):
        body = client.get(path).text
        assert economy.SERVER_ONLY not in body and "steady_" not in body


def test_the_client_gets_prices_odds_and_its_input_guard():
    got = TestClient(main.app).get("/api/economy", headers={"X-Client-Version": "1.2.4"}).json()
    data, _ = economy.load(economy.EXAMPLE)
    cfg = main.game.cfg
    # The schedule of limited pools stays on the server (tests/test_banners.py covers what a client is sent).
    data["resonance"] = {k: v for k, v in data["resonance"].items() if k != "banners"}
    assert got == {**data, "tapGuard": {"fastPerSecond": cfg.fast_taps_per_sec, "fastStreakSec": cfg.fast_streak_sec,
                                        "cooldownSec": cfg.tap_cooldown_sec}}


def test_an_older_client_sees_the_limited_odds_in_common_as_its_draws_have_them():
    data, _ = economy.load(economy.EXAMPLE)
    rates = data["resonance"]["rates"]
    client = TestClient(main.app)
    for version in ("1.2.3", "1.2.2", ""):
        headers = {"X-Client-Version": version} if version else {}
        got = client.get("/api/economy", headers=headers).json()["resonance"]
        assert "limited" not in got["rates"]
        assert got["rates"]["common"] == pytest.approx(rates["common"] + rates["limited"])
        assert {k: v for k, v in got["rates"].items() if k != "common"} == \
            {k: v for k, v in rates.items() if k not in ("common", "limited")}
        # and no holo chance: those clients get no holo versions
        assert "holoChance" not in got
        assert {k: v for k, v in got.items() if k != "rates"} == \
            {k: v for k, v in data["resonance"].items() if k not in ("rates", "holoChance", "banners")}


def test_anti_cheat_settings_override_the_defaults(tmp_path):
    path = tmp_path / "economy.json"
    raw = json.loads(economy.EXAMPLE.read_text(encoding="utf-8"))
    # The steady_* settings belonged to a rule that moved to the guard: a file that still has them loads.
    raw["antiCheat"] = {"tap_cooldown_sec": 90.0, "fast_taps_per_sec": 25, "steady_tolerance": 0.05}
    path.write_text(json.dumps(raw), encoding="utf-8")
    m = Manifest.load(economy=path)
    cfg = economy.drop_config(m.anti_cheat)
    assert (cfg.tap_cooldown_sec, cfg.fast_taps_per_sec) == (90.0, 25)
    assert cfg.fast_streak_sec == DropConfig().fast_streak_sec
    assert m.economy == {k: v for k, v in raw.items() if k != "antiCheat" and not k.startswith("_")}


def test_an_unknown_anti_cheat_setting_is_refused():
    with pytest.raises(ValueError, match="fast_taps_per_second"):
        economy.drop_config({**asdict(DropConfig()), "fast_taps_per_second": 12})


def test_the_example_names_the_scratch_emote_set():
    m = Manifest.load()
    assert m.scratch_emotes and m.economy["park"]["scratch"]["cards"]["basic"]["emote"]["set"] == m.scratch["emote"]["set"]
