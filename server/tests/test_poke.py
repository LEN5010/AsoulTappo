"""Poking another member: the room sees the pet bounce, the member poked is told, with cooldowns."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app, manager
from app.rooms import POKE_INTERVAL, POKE_SAME_INTERVAL, PokeRefused, RoomManager


class Sock:
    def __init__(self):
        self.got = []

    async def send_json(self, data):
        self.got.append(data)

    async def close(self, code=1000):
        pass


def room(*names):
    m = RoomManager()
    peers = [m.join("p", n, "c", Sock()) for n in names]
    return m, peers


def test_everyone_hears_a_poke_and_a_member_turning_invites_down_gets_it_quietly():
    async def go():
        m, (a, b, c) = room("a", "b", "c")
        m.poke("p", a, b.id, 100.0)
        await asyncio.sleep(0)
        message = {"type": "poke", "from": a.id, "to": b.id}
        assert a.ws.got == [message] and b.ws.got == [message] and c.ws.got == [message]
        c.dnd = True
        m.poke("p", b, c.id, 100.0)
        await asyncio.sleep(0)
        assert c.ws.got[-1] == {"type": "poke", "from": b.id, "to": c.id, "quiet": True}
        assert a.ws.got[-1] == {"type": "poke", "from": b.id, "to": c.id}
    asyncio.run(go())


def test_pokes_wait_between_any_two_and_longer_for_the_same_member():
    async def go():
        m, (a, b, c) = room("a", "b", "c")
        m.poke("p", a, b.id, 0.0)
        with pytest.raises(PokeRefused) as refused:
            m.poke("p", a, c.id, POKE_INTERVAL - .1)
        assert refused.value.code == "poke_cooldown"
        m.poke("p", a, c.id, POKE_INTERVAL)
        with pytest.raises(PokeRefused):
            m.poke("p", a, b.id, POKE_SAME_INTERVAL - .1)
        m.poke("p", a, b.id, POKE_SAME_INTERVAL)
        # Poking back is a poke of its own, with its own cooldown.
        m.poke("p", b, a.id, POKE_SAME_INTERVAL)
    asyncio.run(go())


def test_only_another_member_of_the_same_room_can_be_poked():
    async def go():
        m, (a, b) = room("a", "b")
        far = m.join("elsewhere", "far", "c", Sock())
        for target in (a.id, far.id, "nobody"):
            with pytest.raises(PokeRefused) as refused:
                m.poke("p", a, target, 0.0)
            assert refused.value.code == "no_member"
        # A refusal costs no cooldown.
        m.poke("p", a, b.id, 0.0)
    asyncio.run(go())


def test_the_cooldown_list_forgets_members_who_left():
    async def go():
        m, (a, b, c) = room("a", "b", "c")
        m.poke("p", a, b.id, 0.0)
        m.leave("p", b.id)
        m.poke("p", a, c.id, POKE_INTERVAL)
        assert set(a.poked) == {c.id}
    asyncio.run(go())


def test_the_server_offers_pokes_when_joining_and_answers_over_the_socket():
    manager.rooms.clear()
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as a, client.websocket_connect('/ws') as b:
            a.send_json({'type': 'join', 'room': 'pokes', 'nick': 'a', 'motionVersion': 3})
            ja = a.receive_json()
            assert ja['features'] == ['poke', 'profile', 'cheer', 'status']
            # A client that announces no motion version is an older one: its `joined` keeps the 1.1 shape.
            b.send_json({'type': 'join', 'room': 'pokes', 'nick': 'b', 'dnd': True})
            jb = b.receive_json()
            assert 'features' not in jb
            a.receive_json()  # b joined
            a.send_json({'type': 'poke', 'id': jb['you']})
            assert a.receive_json() == {'type': 'poke', 'from': ja['you'], 'to': jb['you']}
            assert b.receive_json() == {'type': 'poke', 'from': ja['you'], 'to': jb['you'], 'quiet': True}
            a.send_json({'type': 'poke', 'id': jb['you']})
            assert a.receive_json()['code'] == 'poke_cooldown'
            a.send_json({'type': 'poke', 'id': 'nobody'})
            assert a.receive_json()['code'] == 'no_member'
            a.send_json({'type': 'poke', 'id': ''})
            assert a.receive_json()['code'] == 'bad_message'
