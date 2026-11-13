"""What the main site's admin pages read about saves, rooms and odd play. Days are China Standard Time dates."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from .notice import version_key
from .store import DAY_OFFSET, day_of
from .tracking import COUNT_KEYS

if TYPE_CHECKING:
    from .game import Game

# Days after its first day on which a new save counts as back.
RETENTION_AFTER = (1, 3, 7)
# Saves active within this many days make up the version and collection mixes.
ACTIVE_DAYS = 7
# Room samples of the last day, folded into points of this many minutes (the largest sample of each).
RECENT_STEP = 10
ANOMALY_LIMIT = 50
# Saves listed by credited taps.
HEAVY_LIMIT = 20
# Ledger sources a save does not earn by playing; left out of the shard anomaly list.
UNEARNED = frozenset({"starter", "update", "admin", "redeem"})


def _days(today: str, days: int) -> list[str]:
    end = date.fromisoformat(today)
    return [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _plus(day: str, n: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def _mix(values: list[str]) -> list[dict[str, Any]]:
    return [{"name": name, "count": n} for name, n in Counter(values).most_common()]


def insights(game: Game, days: int) -> dict[str, Any]:
    """New saves and how many came back, the clients and card collections of recently active saves, and what
    draws gave per day and rarity."""
    now = game.now()
    today = day_of(now)
    labels = _days(today, days)
    cohorts = {r["day"]: r for r in game.store.retention(labels[0], DAY_OFFSET, RETENTION_AFTER)}
    retention = []
    for day in labels:
        row = cohorts.get(day, {})
        # A day still under way is not a full count yet.
        retention.append({"day": day, "size": row.get("size", 0),
                          **{f"d{n}": row.get(f"d{n}", 0) if _plus(day, n) < today else None for n in RETENTION_AFTER}})

    active = game.store.active_saves(_days(today, ACTIVE_DAYS)[0])
    ids = {r["id"] for r in active}
    # Newest version first; "other" and "unknown" last.
    versions = sorted(_mix([r["client_version"] or "unknown" for r in active]),
                      key=lambda m: (version_key(m["name"]) is not None, version_key(m["name"]) or ()), reverse=True)
    cards = [f"card:{cid}" for cid in game.manifest.cards]
    held = {r["player_id"]: r["cards"] for r in game.store.card_counts(cards, []) if r["player_id"] in ids}
    collection = [0] * (len(cards) + 1)
    for pid in ids:
        collection[held.get(pid, 0)] += 1

    drops: dict[str, dict[str, dict[str, int]]] = {d: {} for d in labels}
    start = _start_of(labels[0])
    for r in game.store.drops_by_day(start, DAY_OFFSET):
        if r["day"] in drops:
            drops[r["day"]][r["rarity"]] = {"count": r["count"], "new": r["new"] or 0}

    return {
        "today": today,
        "retention": retention,
        "activeDays": ACTIVE_DAYS,
        "active": len(active),
        "versions": versions,
        "collection": {"total": len(cards), "saves": collection},
        "drops": [{"day": d, "rarities": drops[d]} for d in labels],
        "rarities": {**{k: v.get("name", k) for k, v in (game.manifest.data.get("rarities") or {}).items()},
                     "skin": "皮肤"},
    }


def _start_of(day: str) -> float:
    """Unix seconds at the start of China date [day]."""
    d = date.fromisoformat(day)
    return (d.toordinal() - date(1970, 1, 1).toordinal()) * 86400 - DAY_OFFSET


def online(game: Game, days: int, now_numbers: dict[str, int]) -> dict[str, Any]:
    """Room occupancy per day and over the last day, interaction counts, duels and cheer rounds."""
    now = game.now()
    today = day_of(now)
    labels = _days(today, days)
    per_day: dict[str, list[dict[str, Any]]] = {d: [] for d in labels}
    recent: dict[int, dict[str, int]] = {}
    step = RECENT_STEP * 60
    since_recent = int(now // step * step) - 24 * 3600 + step
    # The last 24 hours reach into yesterday when fewer than two days are asked for.
    for s in game.store.room_samples(min(int(_start_of(labels[0])), since_recent)):
        day = day_of(s["ts"])
        if day in per_day:
            per_day[day].append(s)
        if s["ts"] >= since_recent:
            point = recent.setdefault(s["ts"] // step * step, {"rooms": 0, "members": 0, "saves": 0})
            for k in point:
                point[k] = max(point[k], s[k])

    counts: dict[str, dict[str, int]] = {d: {} for d in labels}
    for r in game.store.daily_counts(labels[0]):
        if r["day"] in counts:
            counts[r["day"]][r["key"]] = r["count"]
    duels: dict[str, dict[str, Any]] = {d: {"played": 0, "bets": {}} for d in labels}
    for r in game.store.duels_by_day(_start_of(labels[0]), DAY_OFFSET):
        if r["day"] in duels:
            duels[r["day"]]["played"] += r["count"]
            bets = duels[r["day"]]["bets"]
            bets[str(r["bet"])] = bets.get(str(r["bet"]), 0) + r["count"]
    cheer = {r["day"]: r for r in game.store.ledger_by_day(labels[0], "cheer")}

    series = []
    for day in labels:
        samples = per_day[day]
        members = [s["members"] for s in samples]
        series.append({
            "day": day, "samples": len(samples),
            "peakMembers": max(members, default=0), "peakRooms": max((s["rooms"] for s in samples), default=0),
            "peakSaves": max((s["saves"] for s in samples), default=0),
            "avgMembers": round(sum(members) / len(members), 1) if members else 0,
            # Minutes with at least two saves in one room.
            "sharedMinutes": sum(1 for s in samples if s["largest"] >= 2),
            "counts": {k: counts[day].get(k, 0) for k in COUNT_KEYS},
            "duels": duels[day],
            "cheer": {"shards": cheer.get(day, {}).get("amount") or 0, "saves": cheer.get(day, {}).get("saves") or 0},
        })
    return {"today": today, "now": now_numbers, "series": series,
            "recent": [{"ts": ts, **v} for ts, v in sorted(recent.items())], "recentStep": RECENT_STEP}


def anomalies(game: Game, day: str | None) -> dict[str, Any]:
    """Saves of [day] (default today) whose taps look automated: those that set off a cooldown or had taps dropped,
    and those with the most credited taps (an auto-clicker that varies its rate and stays below the cooldown rate
    shows only there). Also the saves that gained the most shards by playing that day."""
    day = day or day_of(game.now())

    def tap_row(r: dict[str, Any]) -> dict[str, Any]:
        return {"player": r["player_id"], "userId": r["main_user_id"], "credited": r["credited"], "dropped": r["dropped"],
                "serverCooldowns": r["server_cooldowns"], "clientCooldowns": r["client_cooldowns"],
                "steadyCooldowns": r["steady"], "tapShards": r["shards"]}

    taps = [tap_row(r) for r in game.store.tap_flags_of(day, ANOMALY_LIMIT)]
    heavy = [tap_row(r) for r in game.store.top_tappers(day, HEAVY_LIMIT)]
    gained: dict[str, dict[str, Any]] = {}
    for r in game.store.ledger_day(day):
        if r["source"] in UNEARNED or r["amount"] <= 0:
            continue
        row = gained.setdefault(r["player_id"], {"player": r["player_id"], "userId": r["main_user_id"],
                                                 "gained": 0, "sources": {}})
        row["gained"] += r["amount"]
        row["sources"][r["source"]] = r["amount"]
    shards = sorted(gained.values(), key=lambda r: -r["gained"])[:ANOMALY_LIMIT]
    return {"day": day, "tapCap": game.manifest.income["dailyCap"], "taps": taps, "heavy": heavy, "shards": shards}
