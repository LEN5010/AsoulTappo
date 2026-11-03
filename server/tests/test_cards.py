import random

from app.cards import DropConfig, next_pity, pick_card, roll_rarity

from fixtures import SeqRng, tiny_manifest

W = {"common": 70, "rare": 22, "epic": 7, "legendary": 1}
CFG = DropConfig()


def test_roll_follows_weights_boundaries():
    assert roll_rarity(W, 0, 0, CFG, SeqRng(0.0)) == "common"
    assert roll_rarity(W, 0, 0, CFG, SeqRng(0.70)) == "rare"      # 70/100 starts "rare"
    assert roll_rarity(W, 0, 0, CFG, SeqRng(0.92)) == "epic"
    assert roll_rarity(W, 0, 0, CFG, SeqRng(0.995)) == "legendary"


def test_distribution_roughly_matches_weights():
    rng = random.Random(1234)
    counts = {r: 0 for r in W}
    since_e = since_l = 0
    n = 20000
    for _ in range(n):
        r = roll_rarity(W, since_e, since_l, CFG, rng)
        counts[r] += 1
        since_e, since_l = next_pity(r, since_e, since_l)
    assert 0.66 < counts["common"] / n < 0.74
    assert counts["legendary"] > 0
    assert counts["epic"] / n > 0.06  # pity only ever raises it


def test_epic_hard_pity_and_soft_pity_ramp():
    # 19 opens without epic -> the 20th is epic or better whatever the roll
    assert roll_rarity(W, 19, 0, CFG, SeqRng(0.0)) in ("epic", "legendary")
    assert roll_rarity(W, 19, 0, CFG, SeqRng(0.0)) == "epic"
    # soft pity: epic weight grows after 10 misses, so a roll that is "rare" at 0 becomes epic
    assert roll_rarity(W, 0, 0, CFG, SeqRng(0.95)) == "epic"
    base = roll_rarity(W, 5, 0, CFG, SeqRng(0.85))
    ramp = roll_rarity(W, 17, 0, CFG, SeqRng(0.85))
    assert base == "rare" and ramp == "epic"


def test_legendary_hard_pity():
    assert roll_rarity(W, 5, 59, CFG, SeqRng(0.0)) == "legendary"


def test_next_pity():
    assert next_pity("common", 3, 4) == (4, 5)
    assert next_pity("epic", 3, 4) == (0, 5)
    assert next_pity("legendary", 3, 4) == (0, 0)


def test_pick_prefers_unowned_and_falls_back():
    m = tiny_manifest()
    # c1 owned (weight 1) vs c2 unowned (weight 3): total 4 -> x<0.25 picks c1, else c2
    assert pick_card(m.by_rarity, {"c1"}, "common", CFG, SeqRng(0.1))["id"] == "c1"
    assert pick_card(m.by_rarity, {"c1"}, "common", CFG, SeqRng(0.3))["id"] == "c2"
    # empty rarity falls back to the next lower one
    by = {**m.by_rarity, "epic": []}
    assert pick_card(by, {}, "epic", CFG, SeqRng(0.0))["rarity"] == "rare"
