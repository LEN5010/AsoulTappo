"""AsoulTappo network layer (STUB — not wired into the UI yet).

Part of AsoulTappo (GPL-2.0). See protocol/PROTOCOL.md for the wire format.

TODO hook point: client/input_handler.py -> InputHandler._on_key_press /
_on_mouse_click. Call ``TapBatcher.add()`` there (count only; never pass the
key identity) and let the batcher flush to ``RoomClient.send_tap(count)``.
"""
from .client import NullRoomClient, RoomClient, RoomEvents, TapBatcher

__all__ = ["RoomClient", "NullRoomClient", "RoomEvents", "TapBatcher"]
