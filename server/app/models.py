"""Pydantic message models for the AsoulTappo WebSocket protocol.

See protocol/PROTOCOL.md. Privacy rule: only *counts* of taps are ever sent;
the server never receives key / mouse content.
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


class LeaveMsg(_Msg):
    type: Literal["leave"] = "leave"


class TapMsg(_Msg):
    type: Literal["tap"] = "tap"
    count: int = Field(ge=1, le=MAX_TAP_BATCH)


class EmoteMsg(_Msg):
    type: Literal["emote"] = "emote"
    emote: str = Field(min_length=1, max_length=32)


class StateMsg(_Msg):
    """Update own profile. Send `character` and/or `nick` (at least one)."""

    type: Literal["state"] = "state"
    character: Optional[str] = Field(default=None, min_length=1, max_length=32)
    nick: Optional[str] = Field(default=None, min_length=1, max_length=MAX_NICK_LEN)

    @model_validator(mode="after")
    def _at_least_one(self) -> "StateMsg":
        if self.character is None and self.nick is None:
            raise ValueError("state needs character and/or nick")
        return self


class PingMsg(_Msg):
    type: Literal["ping"] = "ping"


ClientMessage = Annotated[
    Union[JoinMsg, LeaveMsg, TapMsg, EmoteMsg, StateMsg, PingMsg],
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter = TypeAdapter(ClientMessage)


# ---------------- server -> client ----------------
class Member(BaseModel):
    id: str
    nick: str
    character: str
    taps: int = 0


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


class PongMsg(BaseModel):
    type: Literal["pong"] = "pong"


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    code: str  # room_full | bad_message | not_joined | already_joined
    message: str = ""
