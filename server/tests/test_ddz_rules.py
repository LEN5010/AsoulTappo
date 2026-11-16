"""Dou dizhu hands: classify() against every hand listed out the way onestraw/doudizhu lists them, and the fixture
the client's copy of the rules is checked against."""
import itertools
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from app.ddz_rules import ACE, BIG_JOKER, SMALL_JOKER, Hand, beats, bombs, classify, hand_beats, rank, ranks

FIXTURE = Path(__file__).resolve().parents[2] / "client/src/ddz/rules.fixture.json"
PLAIN = list(range(3, 16))  # 3..2
ALL = PLAIN + [SMALL_JOKER, BIG_JOKER]
CHAIN = list(range(3, ACE + 1))  # 3..A


def cards_of(rs):
    """Cards with the ranks [rs], taking each rank's suits in order."""
    used = Counter()
    out = []
    for r in rs:
        out.append((r - 3) * 4 + used[r] if r < SMALL_JOKER else 52 + r - SMALL_JOKER)
        used[r] += 1
    return out


def listed():
    """rank multiset -> {Hand}: every hand, built up from its parts, the way onestraw/doudizhu fills its table."""
    table = defaultdict(set)

    def put(rs, kind, size, main):
        if max(Counter(rs).values()) <= 4 and Counter(rs)[SMALL_JOKER] <= 1 and Counter(rs)[BIG_JOKER] <= 1:
            table[tuple(sorted(rs))].add(Hand(kind, size, main))

    def runs(size):
        return [CHAIN[i:i + size] for i in range(len(CHAIN) - size + 1)]

    for r in ALL:
        put([r], "solo", 1, r)
    for r in PLAIN:
        put([r] * 2, "pair", 1, r)
        put([r] * 3, "trio", 1, r)
        put([r] * 4, "bomb", 1, r)
        for k in ALL:
            if k != r:
                put([r] * 3 + [k], "trio1", 1, r)
        for k in PLAIN:
            if k != r:
                put([r] * 3 + [k] * 2, "trio2", 1, r)
        for a, b in itertools.combinations_with_replacement([k for k in ALL if k != r], 2):
            put([r] * 4 + [a, b], "four2", 1, r)
        for a, b in itertools.combinations_with_replacement([k for k in PLAIN if k != r], 2):
            put([r] * 4 + [a] * 2 + [b] * 2, "four22", 1, r)
    put([SMALL_JOKER, BIG_JOKER], "rocket", 1, BIG_JOKER)
    for size in range(5, 13):
        for run in runs(size):
            put(run, "straight", size, run[-1])
    for size in range(3, 11):
        for run in runs(size):
            put(run * 2, "pairs", size, run[-1])
    for size in range(2, 7):
        for run in runs(size):
            put(run * 3, "plane", size, run[-1])
    for size in range(2, 6):
        for run in runs(size):
            for kick in itertools.combinations_with_replacement([k for k in ALL if k not in run], size):
                put(run * 3 + list(kick), "plane1", size, run[-1])
    for size in range(2, 5):
        for run in runs(size):
            for kick in itertools.combinations_with_replacement([k for k in PLAIN if k not in run], size):
                put(run * 3 + list(kick) * 2, "plane2", size, run[-1])
    return table


TABLE = listed()


def test_ranks_of_the_deck():
    assert [rank(c) for c in (0, 3, 4, 47, 48, 51, 52, 53)] == [3, 3, 4, 14, 15, 15, 16, 17]
    assert Counter(rank(c) for c in range(54)) == Counter({**{r: 4 for r in PLAIN}, SMALL_JOKER: 1, BIG_JOKER: 1})


def test_the_table_is_as_large_as_the_engine_it_follows():
    # onestraw/doudizhu counts 34152 entries over its 37 kinds; a few of its kinds, as it sizes them.
    sizes = Counter((h.kind, h.size) for hands in TABLE.values() for h in hands)
    assert sum(sizes.values()) == 34152 and len(sizes) == 37
    assert [sizes[k] for k in (("trio1", 1), ("plane1", 2), ("plane1", 5), ("trio2", 1), ("plane2", 4), ("four2", 1),
                               ("four22", 1))] == [182, 979, 12512, 156, 3726, 1339, 1014]


def test_every_listed_hand_is_read_as_listed():
    for rs, hands in TABLE.items():
        assert set(classify(cards_of(rs))) == hands, rs


def test_cards_that_are_no_hand_are_read_as_none():
    rng = random.Random(7)
    seen = 0
    while seen < 4000:
        cards = rng.sample(range(54), rng.randint(1, 12))
        if tuple(ranks(cards)) not in TABLE:
            assert classify(cards) == [], ranks(cards)
            seen += 1
    assert classify([]) == []


def test_suits_and_order_do_not_matter():
    assert classify([0, 5, 9]) == classify([10, 7, 2]) == []
    assert classify([3, 1, 2]) == [Hand("trio", 1, 3)]
    assert classify([52, 53]) == classify([53, 52]) == [Hand("rocket", 1, BIG_JOKER)]


def test_what_beats_what():
    solo3, solo4, pair3 = cards_of([3]), cards_of([4]), cards_of([3, 3])
    bomb3, bomb4, rocket = cards_of([3] * 4), cards_of([4] * 4), cards_of([SMALL_JOKER, BIG_JOKER])
    assert beats(solo4, solo3) and not beats(solo3, solo4) and not beats(solo3, solo3)
    assert not beats(pair3, solo3) and not beats(solo4, pair3)
    assert beats(bomb3, cards_of([15, 15])) and beats(bomb4, bomb3) and not beats(bomb3, bomb4)
    assert beats(rocket, bomb4) and not beats(bomb4, rocket) and not beats(cards_of([15] * 4), rocket)
    # Runs are compared only at the same length.
    assert beats(cards_of([4, 5, 6, 7, 8]), cards_of([3, 4, 5, 6, 7]))
    assert not beats(cards_of([4, 5, 6, 7, 8, 9]), cards_of([3, 4, 5, 6, 7]))
    # What goes along does not count.
    assert beats(cards_of([4, 4, 4, 3]), cards_of([3, 3, 3, 15]))
    assert not beats(cards_of([3, 3, 3, 15]), cards_of([4, 4, 4, 5]))
    assert not beats([], solo3) and not beats(cards_of([3, 4]), solo3)
    # Read two ways, either reading may win.
    twelve = cards_of([3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6])
    assert beats(cards_of([7, 7, 7, 8, 8, 8, 9, 9, 9, 3, 4, 5]), twelve)
    assert beats(cards_of([7] * 3 + [8] * 3 + [9] * 3 + [10] * 3), twelve)


def test_bombs_and_the_rocket_double():
    assert bombs(cards_of([9] * 4)) == 1 and bombs(cards_of([SMALL_JOKER, BIG_JOKER])) == 1
    assert bombs(cards_of([9] * 4 + [3, 4])) == 0 and bombs(cards_of([9])) == 0


def build_fixture():
    """Hands of every kind, cards that are none, and pairs to compare: what the client's rules must answer too."""
    rng = random.Random(20261116)
    by_kind = defaultdict(list)
    for rs, hands in TABLE.items():
        for h in hands:
            by_kind[h.kind].append(rs)
    reads = []
    for kind in sorted(by_kind):
        for rs in rng.sample(sorted(by_kind[kind]), min(40, len(by_kind[kind]))):
            reads.append(cards_of(rs))
    both = [rs for rs, hands in sorted(TABLE.items()) if len(hands) > 1]
    reads += [cards_of(rs) for rs in rng.sample(both, min(60, len(both)))]
    while len(reads) < 900:
        reads.append(sorted(rng.sample(range(54), rng.randint(1, 12))))
    pairs = []
    while len(pairs) < 600:
        a, b = rng.choice(reads[:660]), rng.choice(reads[:660])
        if len(pairs) % 3 and len(a) != len(b) and not bombs(a) and not bombs(b):
            continue  # mostly pairs that could be compared
        pairs.append([a, b])
    return {
        "reads": [[cards, [list(h) for h in classify(cards)]] for cards in reads],
        "beats": [[a, b, beats(a, b)] for a, b in pairs],
    }


def test_the_fixture_the_client_checks_against_is_current():
    # Regenerate with: python -c "import tests.test_ddz_rules as t; t.write_fixture()" from server/.
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == build_fixture()


def write_fixture():
    FIXTURE.write_text(json.dumps(build_fixture(), separators=(",", ":")) + "\n", encoding="utf-8")


def test_hand_beats_needs_the_same_kind_and_size():
    assert not hand_beats(Hand("plane1", 2, 9), Hand("plane1", 3, 5))
    assert not hand_beats(Hand("pairs", 3, 9), Hand("straight", 3, 5))
