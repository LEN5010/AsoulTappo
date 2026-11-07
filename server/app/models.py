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
    # optional secret player token: lets the server show the player's unlocked frame/badge
    token: Optional[str] = Field(default=None, max_length=128)
    # main-site Bearer token; wins over token once the account has a save
    accountToken: Optional[str] = Field(default=None, max_length=512)
    # big hidden card worn as a name plate; dropped unless the save owns it
    plate: Optional[str] = Field(default=None, max_length=64)


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


ClientMessage = Annotated[
    Union[JoinMsg, LeaveMsg, TapMsg, MotionMsg, EmoteMsg, StateMsg, PingMsg],
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
    # big hidden card id worn as a name plate, null for none
    plate: Optional[str] = None


class JoinedMsg(BaseModel):
    type: Literal["joined"] = "joined"
    room: str
    you: str
    members: list[Member]


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


class PongMsg(BaseModel):
    type: Literal["pong"] = "pong"


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    # room_full | bad_message | not_joined | already_joined | locked | bad_decor | bad_item | rate_limited
    code: str
    message: str = ""
