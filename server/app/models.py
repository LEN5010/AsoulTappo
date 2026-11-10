"""Pydantic message models for the AsoulTappo WebSocket protocol.

See protocol/PROTOCOL.md. Room input carries counts and bounded pet animation offsets.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, model_validator

MAX_NICK_LEN = 24
MAX_TAP_BATCH = 500  # sanity cap per tap message


class _Msg(BaseModel):
    model_config = {"extra": "ignore"}


# ---------------- client -> server ----------------
class JoinMsg(_Msg):
    type: Literal["join"] = "join"
    room: str = Field(min_length=1, max_length=64)
    nick: str = Field(min_length=1, max_length=MAX_NICK_LEN)
    character: str = Field(default="default", max_length=32)
    # optional secret player token: the save that unlocks skins, emotes and the plate, and gives a uid
    token: Optional[str] = Field(default=None, max_length=128)
    # main-site Bearer token; wins over token once the account has a save
    accountToken: Optional[str] = Field(default=None, max_length=512)
    # name plate (a big hidden card id or a manifest `plates` id); dropped unless the save has unlocked it
    plate: Optional[str] = Field(default=None, max_length=64)
    # turns down rock-paper-scissors invites; servers before 1.2 ignore it
    dnd: bool = False


class LeaveMsg(_Msg):
    type: Literal["leave"] = "leave"


class TapMsg(_Msg):
    type: Literal["tap"] = "tap"
    count: int = Field(ge=1, le=MAX_TAP_BATCH)


class EmoteMsg(_Msg):
    type: Literal["emote"] = "emote"
    emote: str = Field(min_length=1, max_length=32)


class PetMotion(_Msg):
    dx: float = Field(ge=-20, le=20, allow_inf_nan=False)
    dy: float = Field(ge=-20, le=20, allow_inf_nan=False)
    keyDown: bool
    left: bool
    right: bool


class MotionMsg(PetMotion):
    type: Literal["motion"] = "motion"


class StateMsg(_Msg):
    """Update the displayed character, nickname or name plate ("" takes the plate off)."""

    type: Literal["state"] = "state"
    character: Optional[str] = Field(default=None, min_length=1, max_length=32)
    nick: Optional[str] = Field(default=None, min_length=1, max_length=MAX_NICK_LEN)
    plate: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _at_least_one(self) -> "StateMsg":
        if all(v is None for v in (self.character, self.nick, self.plate)):
            raise ValueError("state needs character, nick or plate")
        return self


class PingMsg(_Msg):
    type: Literal["ping"] = "ping"


class SetPublicMsg(_Msg):
    """Host only: list the room in GET /rooms or take it off."""

    type: Literal["set_public"] = "set_public"
    public: bool


class KickMsg(_Msg):
    """Host only: remove a member; a member with a save stays out until the room closes."""

    type: Literal["kick"] = "kick"
    id: str = Field(min_length=1, max_length=32)


Hand = Literal["rock", "paper", "scissors"]


class DndMsg(_Msg):
    """Turn rock-paper-scissors invites down (true) or let them through again."""

    type: Literal["dnd"] = "dnd"
    dnd: bool


class DuelInviteMsg(_Msg):
    """Invite another member of the room to rock-paper-scissors at one of the manifest's bets."""

    type: Literal["duel_invite"] = "duel_invite"
    id: str = Field(min_length=1, max_length=32)
    bet: int = Field(ge=1, le=10**9)


class DuelAnswerMsg(_Msg):
    type: Literal["duel_answer"] = "duel_answer"
    duel: str = Field(min_length=1, max_length=32)
    accept: bool


class DuelThrowMsg(_Msg):
    type: Literal["duel_throw"] = "duel_throw"
    duel: str = Field(min_length=1, max_length=32)
    hand: Hand


ClientMessage = Annotated[
    Union[JoinMsg, LeaveMsg, TapMsg, MotionMsg, EmoteMsg, StateMsg, PingMsg, SetPublicMsg, KickMsg,
          DndMsg, DuelInviteMsg, DuelAnswerMsg, DuelThrowMsg],
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter = TypeAdapter(ClientMessage)


# ---------------- server -> client ----------------
class Member(BaseModel):
    id: str
    # stable per room for players with a token (a hash of player id + room), else null
    uid: Optional[str] = None
    nick: str
    character: str
    taps: int = 0
    motion: Optional[PetMotion] = None
    # name plate worn: a big hidden card id or a manifest `plates` id, null for none
    plate: Optional[str] = None


class RoomInfo(BaseModel):
    """Room-wide state; clients from before 1.2 never read it."""

    host: Optional[str] = None  # member id
    public: bool = False


class JoinedMsg(BaseModel):
    type: Literal["joined"] = "joined"
    room: str
    you: str
    members: list[Member]
    info: RoomInfo


class RoomInfoMsg(RoomInfo):
    """Sent to the whole room when the host or the public flag changes."""

    type: Literal["room_info"] = "room_info"


class MemberJoinedMsg(BaseModel):
    type: Literal["member_joined"] = "member_joined"
    member: Member


class MemberLeftMsg(BaseModel):
    type: Literal["member_left"] = "member_left"
    id: str


class TapBroadcast(BaseModel):
    type: Literal["tap"] = "tap"
    id: str
    count: int
    total: int  # that member's total taps in this room


class EmoteBroadcast(BaseModel):
    type: Literal["emote"] = "emote"
    id: str
    emote: str


class StateBroadcast(BaseModel):
    type: Literal["state"] = "state"
    id: str
    character: str
    nick: str
    plate: Optional[str] = None


class ScratchBroadcast(BaseModel):
    """A member's scratch card paid enough shards to tell the room."""

    type: Literal["scratch"] = "scratch"
    id: str
    shards: int


class DuelInvited(BaseModel):
    """To both sides of a new invite: [from_] invited [to], who has `sec` seconds to answer."""

    model_config = {"populate_by_name": True}
    type: Literal["duel_invite"] = "duel_invite"
    duel: str
    from_: str = Field(alias="from")
    to: str
    bet: int
    prize: int
    sec: int


class DuelStarted(BaseModel):
    """To both sides: the bets are taken, round 1 has `sec` seconds."""

    type: Literal["duel_start"] = "duel_start"
    duel: str
    round: int
    sec: int


class DuelRound(BaseModel):
    """To both sides after a draw: the hands of the draw by member id, and the next round."""

    type: Literal["duel_round"] = "duel_round"
    duel: str
    round: int
    sec: int
    hands: dict[str, str]


class DuelResult(BaseModel):
    """To the whole room: who won `prize` and who lost, and the last hands by member id (null: none thrown)."""

    type: Literal["duel_result"] = "duel_result"
    duel: str
    winner: str
    loser: str
    prize: int
    hands: dict[str, Optional[str]]


class DuelOver(BaseModel):
    """To both sides: the invite or duel ended without a winner. reason: declined | timeout | gone | no_shards |
    duel_cap | idle | draws; after idle and draws both bets went back."""

    type: Literal["duel_over"] = "duel_over"
    duel: str
    reason: str


class PongMsg(BaseModel):
    type: Literal["pong"] = "pong"


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    # room_full | bad_message | not_joined | already_joined | locked | rate_limited | not_host | no_member |
    # host_needs_save | in_duel | no_duel | duel_* (see PROTOCOL.md)
    code: str
    message: str = ""
    # why a room_full ends the session: kicked | banned | need_save. Only room_full makes clients
    # from before 1.2 stop reconnecting, so every final refusal uses that code.
    reason: Optional[str] = None
