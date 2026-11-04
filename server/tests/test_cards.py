import pytest
from app.cards import roll_tier
from fixtures import SeqRng, tiny_manifest

CFG = tiny_manifest().resonance

@pytest.mark.parametrize("x,tier", [(0, "legendary"), (.004999, "legendary"), (.005, "skin"), (.009999, "skin"),
                                    (.01, "epic"), (.054999, "epic"), (.055, "rare"), (.104999, "rare"), (.105, "common"), (.999, "common")])
def test_probability_boundaries(x, tier):
    assert roll_tier(CFG["rates"], set(CFG["rates"]), {"legendary": 0, "skin": 0}, CFG["pity"], SeqRng(x)) == tier

@pytest.mark.parametrize("x", [0, .005, .01, .055])
def test_unavailable_tier_lands_on_common(x):
    assert roll_tier(CFG["rates"], set(), {"legendary": 999, "skin": 999}, CFG["pity"], SeqRng(x)) == "common"
