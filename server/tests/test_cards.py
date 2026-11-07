import pytest
from app.cards import pick_common, pick_weighted, roll_tier
from app.manifest import Manifest
from fixtures import SeqRng, tiny_manifest

CFG = tiny_manifest().resonance

@pytest.mark.parametrize("x,prize", [(0, 0), (.2999, 0), (.30, 1), (.5999, 1), (.60, 2), (.7999, 2), (.80, 3),
                                     (.9199, 3), (.92, 4), (.9799, 4), (.98, 5), (.9999, 5)])
def test_checkin_prize_boundaries(x, prize):
    weights = [p["weight"] for p in Manifest.load().checkin["prizes"]]
    assert pick_weighted(weights, SeqRng(x)) == prize

@pytest.mark.parametrize("x,tier", [(0, "legendary"), (.004999, "legendary"), (.005, "skin"), (.009999, "skin"),
                                    (.01, "epic"), (.054999, "epic"), (.055, "rare"), (.084999, "rare"),
                                    (.085, "uncommon"), (.144999, "uncommon"), (.145, "common"), (.999, "common")])
def test_probability_boundaries(x, tier):
    assert roll_tier(CFG["rates"], set(CFG["rates"]), {"legendary": 0, "skin": 0}, CFG["pity"], SeqRng(x)) == tier

@pytest.mark.parametrize("x", [0, .005, .01, .055, .085])
def test_unavailable_tier_lands_on_common(x):
    assert roll_tier(CFG["rates"], set(), {"legendary": 999, "skin": 999}, CFG["pity"], SeqRng(x)) == "common"


def test_common_odds_follow_kind_weights_instead_of_catalog_sizes():
    from collections import Counter
    pool = [{"id": "card:one", "kind": "card"}] + [
        {"id": f"emote:{i}", "kind": "emote"} for i in range(100)]
    outcomes = Counter(pick_common(pool, CFG["commonKindWeights"], {}, SeqRng((i + .5) / 8550))["kind"]
                       for i in range(8550))
    assert outcomes == {"card": 4500, "emote": 4050}


@pytest.mark.parametrize("kind,roll", [("card", 45 / 85.5 - .000001), ("emote", 45 / 85.5 + .000001)])
def test_completed_common_kind_keeps_its_odds(kind, roll):
    pool = [{"id": "card:one", "kind": "card"}, {"id": "emote:one", "kind": "emote"}]
    owned = {f"{kind}:one": 1}
    assert pick_common(pool, CFG["commonKindWeights"], owned, SeqRng(roll))["id"] == f"{kind}:one"


@pytest.mark.parametrize("kind", ["card", "emote"])
def test_common_supports_catalogs_with_only_one_kind(kind):
    pool = [{"id": f"{kind}:one", "kind": kind}]
    assert pick_common(pool, CFG["commonKindWeights"], {}, SeqRng(.99999)) == pool[0]
