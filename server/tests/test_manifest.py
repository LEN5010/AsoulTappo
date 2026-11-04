"""Integrity of the committed assets: manifest <-> files <-> pack index <-> client copy."""
import hashlib
import json
from pathlib import Path

import pytest

from app.manifest import Manifest, find_packs_dir

REPO = Path(__file__).resolve().parents[2]
PACKS = find_packs_dir()
BUNDLE = REPO / "client" / "public" / "assets"
FIVE = {"嘉然", "乃琳", "贝拉", "心宜", "思诺"}
M = Manifest.load()


def resolve(ref: str) -> Path:
    scheme, rel = ref.split(":", 1)
    base = {"bundle": BUNDLE, "pack": PACKS}[scheme]
    return base / rel


def all_refs(m: dict):
    for t in m["themes"]:
        yield t["cover"]
        if t.get("preview"):
            yield t["preview"]
        for ent in t["icons"].values():
            yield from ent.values()
        for v in t["parts"].values():
            yield from (v if isinstance(v, list) else [v])
    for c in m["cards"]:
        yield c["thumb"]
        yield c["full"]
        if c["video"]:
            yield c["video"]
    for s in m["emoteSets"]:
        for e in s["emotes"]:
            yield e["img"]
    for d in m["decor"]:
        yield d["img"]
    for a in m["accessories"]:
        yield a["img"]
        for pose in ("left", "right"):
            if a.get(pose):
                yield a[pose]


def test_every_referenced_file_exists():
    refs = list(all_refs(M.data))
    assert len(refs) > 400
    missing = [r for r in refs if not resolve(r).is_file()]
    assert not missing[:5]


def test_only_the_five_characters():
    assert {c["name"] for c in M.data["characters"]} == FIVE
    for c in M.data["cards"]:
        assert c["characters"] and set(c["characters"]) <= FIVE
    for t in M.data["themes"]:
        assert set(t["characters"]) <= FIVE
    for s in M.data["emoteSets"]:
        assert s["character"] in FIVE
    assert {t["id"] for t in M.data["themes"]}  # sanity
    # every character has cards, themes and emotes
    for name in FIVE:
        assert any(name in c["characters"] for c in M.data["cards"])
        assert any(name in t["characters"] for t in M.data["themes"])
        assert any(s["character"] == name for s in M.data["emoteSets"])


def test_cards_rarity_rules_and_counts():
    cards = M.data["cards"]
    assert len({c["id"] for c in cards}) == len(cards)
    assert len(cards) == 70
    assert sum(c["tier"] == "big" for c in cards) == 8
    assert sum(c["tier"] == "small" for c in cards) == 8
    assert M.cards["c1748345610010"]["tier"] == "big"
    assert M.cards["c1748345610002"]["tier"] == "normal"
    for s in M.data["series"]:
        assert s["total"] == sum(1 for c in cards if c["series"] == s["id"]) > 0


def test_decor_unlock_rules_are_reachable():
    for d in M.data["decor"]:
        assert d["unlock"]["series"] in M.series_total
        assert 1 <= d["unlock"]["min"] <= M.series_total[d["unlock"]["series"]]
        assert d["kind"] in ("frame", "badge")


def test_accessories_starter_and_economy():
    assert M.data["accessories"] == M.data["decor"] == []
    acc = M.data["accessories"]
    assert len({a["id"] for a in acc}) == len(acc) and all(len(a["id"]) <= 48 for a in acc)
    for a in acc:
        assert a["slot"] in ("head", "desk") and a["rarity"] in M.data["rarities"]
        assert set(a["characters"]) <= FIVE
        assert a["kind"] in ("figure", "anim") and (a["kind"] == "figure") == (a["slot"] == "head")
    # every character can start with a few emotes of their own
    starter = M.data["starter"]["emotes"]
    by_key = {e["key"]: s["character"] for s in M.data["emoteSets"] for e in s["emotes"]}
    assert {by_key[k] for k in starter} == FIVE
    assert M.starter == {f"emote:{k}" for k in starter}
    dropped = {i["id"] for tier in M.resonance_pool.values() for i in tier}
    assert not dropped & M.starter
    assert len(dropped) == 428
    assert len(M.items) == len(dropped) + len(M.starter)
    assert M.craft_cost == {"common": 480, "rare": 1600}


def test_pool_counts_and_card_rarities():
    assert [len(M.resonance_pool[r]) for r in ("common", "rare", "epic", "legendary", "skin")] == [378, 15, 24, 8, 3]
    for c in M.cards.values():
        assert c["rarity"] == ("legendary" if c["tier"] == "big" else "epic" if c["tier"] == "small" or c["video"] else "common")
    assert all(set(r) == {"name"} for r in M.data["rarities"].values())


def test_skin_directories_match_manifest():
    directories = {p.name for p in (REPO / "client/src/assets/characters").iterdir() if p.is_dir()} - FIVE
    assert directories == set(M.skins)


def test_emote_keys_unique_and_fit_wire_limit():
    keys = [e["key"] for s in M.data["emoteSets"] for e in s["emotes"]]
    assert len(keys) == len(set(keys))
    assert all(len(k) <= 32 for k in keys)


def test_default_theme_is_fully_bundled():
    t = next(t for t in M.data["themes"] if t["id"] == M.data["defaultTheme"])
    assert t["pack"] is None
    for v in t["parts"].values():
        for ref in v if isinstance(v, list) else [v]:
            assert ref.startswith("bundle:")
    for t in M.data["themes"]:
        if t["pack"]:
            for v in t["parts"].values():
                for ref in v if isinstance(v, list) else [v]:
                    assert ref.startswith("pack:")


def test_pack_index_matches_files_and_manifest():
    idx = json.loads((PACKS / "index.json").read_text(encoding="utf-8"))
    listed = set()
    for pack in idx["packs"]:
        assert pack["size"] == sum(f["size"] for f in pack["files"])
        for f in pack["files"]:
            p = PACKS / f["path"]
            assert p.stat().st_size == f["size"]
            assert hashlib.sha256(p.read_bytes()).hexdigest() == f["sha256"]
            assert f["size"] < 50_000_000
            listed.add(f["path"])
    pack_refs = {r.split(":", 1)[1] for r in all_refs(M.data) if r.startswith("pack:")}
    assert pack_refs == listed


def test_client_manifest_copy_is_identical():
    client_copy = json.loads((REPO / "client" / "src" / "data" / "manifest.json").read_text(encoding="utf-8"))
    assert client_copy == M.data


def test_no_stray_files_outside_manifest():
    refs = {resolve(r).resolve() for r in all_refs(M.data)}
    for root in (BUNDLE, PACKS):
        for f in root.rglob("*"):
            if f.is_file() and f.name not in ("manifest.json", "index.json"):
                assert f.resolve() in refs, f
