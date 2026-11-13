"""Redeem codes: the main site's admins make them (through /admin/codes), players enter them for shards and park coins.

Generated codes are 12 characters from ALPHABET, shown in three groups of four; an admin may also write a memorable
one. Entering a code ignores case, dashes and spaces. Each save redeems a code once; a code has a number of uses (1 for
the codes handed to one person each, more for one code posted to a group). Checking, counting, paying and the claim row
are one transaction. A save that enters TRIES wrong codes within TRY_WINDOW seconds is locked for LOCK_SECONDS."""
from __future__ import annotations

import json
import math
import secrets
from typing import Any, Callable

from .game import Game, GameError, player_id_for
from .park import REDEEM, Park
from .store import Store, day_of

# Digits and capitals without 0 O 1 I L, which are easy to confuse: 31 characters.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 12
GROUP = 4
CUSTOM_MIN, CUSTOM_MAX = 4, 32
TRIES = 5
TRY_WINDOW = 600
LOCK_SECONDS = 900
# daily_counts key counting lockouts per China day (the admin anomalies page can read it; per save see redeem_locks).
LOCK_COUNT = "redeem_lock"


def normalize(text: str) -> str:
    """A code as stored: upper case, without dashes and whitespace."""
    return "".join(ch for ch in text.upper() if ch != "-" and not ch.isspace())


def shown(code: str, custom: bool) -> str:
    """A generated code in groups of four (K7QM-3XRP-WD9H); a custom one as stored."""
    if custom:
        return code
    return "-".join(code[i:i + GROUP] for i in range(0, len(code), GROUP))


def generate() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


class Locked(GameError):
    """The save may not enter codes for [seconds] more."""

    def __init__(self, seconds: int) -> None:
        super().__init__("too_many_tries", f"输错太多次，{max(1, math.ceil(seconds / 60))} 分钟后再试")
        self.seconds = seconds


class Redeem:
    def __init__(self, game: Callable[[], Game], park: Park) -> None:
        # The game may be replaced (tests), so it is looked up on every call, as in Park.
        self._game = game
        self.park = park

    @property
    def game(self) -> Game:
        return self._game()

    # ----------------------------------------------------------------- players
    def redeem(self, token: str, text: str, require_account: bool) -> dict[str, Any]:
        """Pays the code's reward to the save. [require_account]: the server has main-site accounts, and only saves
        linked to one may redeem (guest saves can be made without end)."""
        g = self.game
        pid = player_id_for(token)
        code = normalize(text)
        error: GameError | None = None
        with g.store.transaction() as st:
            now = g.now()
            if require_account and not st.account_for_player(pid):
                raise GameError("login_required", "登录 Asasfans 账号后才能兑换")
            until = st.redeem_lock(pid)
            if until > now:
                raise Locked(math.ceil(until - now))
            row = st.redeem_code(code) if code else None
            if row is None or row["disabled"] is not None:
                # A wrong code: kept even though the call fails, so the transaction ends normally and raises after.
                error = GameError("bad_code", "兑换码不存在")
                if st.add_redeem_try(pid, now, TRY_WINDOW) >= TRIES:
                    st.lock_redeem(pid, now, now + LOCK_SECONDS)
                    st.add_daily_counts({(day_of(now), LOCK_COUNT): 1})
                    error = Locked(LOCK_SECONDS)
            elif st.redeemed(row["id"], pid):
                raise GameError("already_redeemed", "你已经兑换过这个码")
            elif row["expires"] and row["expires"] <= now:
                raise GameError("code_expired", "兑换码已过期")
            elif not st.claim_redeem_code(row["id"], pid, now):
                raise GameError("code_used_up", "兑换码已被领完")
            else:
                self._pay(st, pid, row["shards"], row["coins"], now)
        if error:
            raise error
        out = {**g.status(token), "redeemed": {"shards": row["shards"], "coins": row["coins"]}}
        if g.manifest.park:
            out["park"] = self.park.state(token)
        return out

    def _pay(self, st: Store, pid: str, shards: int, coins: int, now: float) -> None:
        if shards:
            p = st.get_player(pid, now)
            st.update_player(pid, shards=p["shards"] + shards)
            st.add_ledger(pid, day_of(now), REDEEM, shards)
        self.park.grant(st, pid, coins, REDEEM, now)

    # ------------------------------------------------------------------- admin
    def create(self, shards: int, coins: int, count: int, uses: int, expires: float, note: str, custom: str = "",
               actor: str = "") -> dict[str, Any]:
        """Makes [count] codes of [uses] uses each, or the one code [custom]. Returns them."""
        g = self.game
        now = g.now()
        if shards < 0 or coins < 0 or shards + coins == 0:
            raise GameError("bad_reward", "奖励至少要有碎片或驼币")
        if coins and not g.manifest.park:
            raise GameError("bad_reward", "这个服务器没有乐园，不能发驼币")
        if expires and expires <= now:
            raise GameError("bad_expiry", "过期时间已经过了")
        code = normalize(custom)
        if custom:
            if count != 1:
                raise GameError("bad_count", "自定义兑换码只能生成 1 个")
            if not (CUSTOM_MIN <= len(code) <= CUSTOM_MAX and code.isalnum()):
                raise GameError("bad_code_text", f"自定义兑换码为 {CUSTOM_MIN}-{CUSTOM_MAX} 个字母、数字或汉字")
        ids: list[int] = []
        with g.store.transaction() as st:
            for _ in range(count):
                while True:
                    new_id = st.add_redeem_code(code or generate(), bool(custom), shards, coins, uses, expires, note,
                                                actor, now)
                    if new_id is not None:
                        break
                    if custom:
                        raise GameError("code_taken", "这个兑换码已经有了")
                ids.append(new_id)
            st.add_admin_log(now, actor, "code_create", "", json.dumps(
                {"ids": [ids[0], ids[-1]], "count": count, "shards": shards, "coins": coins, "uses": uses,
                 "expires": expires, "custom": bool(custom)}), note)
        return {"codes": [self._row(st.redeem_code_by_id(i)) for i in ids]}

    def find(self, q: str, limit: int, before: int | None = None) -> dict[str, Any]:
        return {"codes": [self._row(r) for r in self.game.store.redeem_codes(q.strip(), limit, before)]}

    def disable(self, code_id: int, actor: str = "", reason: str = "") -> dict[str, Any]:
        """Stops the code at once. Disabling a disabled code changes nothing and logs nothing."""
        g = self.game
        with g.store.transaction() as st:
            row = st.redeem_code_by_id(code_id)
            if row is None:
                raise GameError("no_code", "没有这个兑换码")
            if row["disabled"] is None:
                now = g.now()
                st.disable_redeem_code(code_id, now)
                st.add_admin_log(now, actor, "code_disable", "", json.dumps(
                    {"id": code_id, "code": shown(row["code"], bool(row["custom"]))}), reason or row["note"])
            row = st.redeem_code_by_id(code_id)
        return self._row(row)

    def claims(self, code_id: int, limit: int) -> dict[str, Any]:
        g = self.game
        row = g.store.redeem_code_by_id(code_id)
        if row is None:
            raise GameError("no_code", "没有这个兑换码")
        return {"code": self._row(row), "claims": [{"player": r["player_id"], "userId": r["main_user_id"], "ts": r["ts"]}
                                                   for r in g.store.redeem_claims(code_id, limit)]}

    @staticmethod
    def _row(r: dict[str, Any]) -> dict[str, Any]:
        return {"id": r["id"], "code": shown(r["code"], bool(r["custom"])), "custom": bool(r["custom"]),
                "shards": r["shards"], "coins": r["coins"], "uses": r["uses"], "used": r["used"],
                "expires": r["expires"] or None, "disabled": r["disabled"], "note": r["note"],
                "createdBy": r["created_by"], "created": r["created"]}
