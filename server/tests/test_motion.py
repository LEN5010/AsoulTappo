import pytest
from fastapi.testclient import TestClient

from app.main import app, manager


def test_motion_is_scoped_to_the_room_and_leaves_taps_unchanged():
    manager.rooms.clear()
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as a, client.websocket_connect('/ws') as b, client.websocket_connect('/ws') as other:
            for ws, room, name in ((a, 'motion', 'a'), (b, 'motion', 'b'), (other, 'elsewhere', 'c')):
                ws.send_json({'type': 'join', 'room': room, 'nick': name})
                joined = ws.receive_json()
                if ws is a:
                    sender = joined['you']
            a.receive_json()  # b joined
            pose = {'type': 'motion', 'dx': 12.5, 'dy': -20, 'keyDown': True, 'left': True, 'right': False}
            a.send_json(pose)
            assert b.receive_json() == {**pose, 'id': sender}
            a.send_json({'type': 'ping'})
            assert a.receive_json() == {'type': 'pong'}  # motion is not echoed
            other.send_json({'type': 'ping'})
            assert other.receive_json() == {'type': 'pong'}
            assert manager.members('motion')[0].taps == 0
            with client.websocket_connect('/ws') as late:
                late.send_json({'type': 'join', 'room': 'motion', 'nick': 'late'})
                initial = late.receive_json()
                assert initial['members'][0]['motion'] == {key: value for key, value in pose.items() if key != 'type'}
                a.receive_json()
                b.receive_json()
            a.receive_json()  # late member left
            b.receive_json()
            a.send_json({**pose, 'dx': 0, 'dy': 0, 'keyDown': False, 'left': False})
            assert b.receive_json()['left'] is False


@pytest.mark.parametrize('dx', [21, -21, 'NaN', 'Infinity'])
def test_motion_requires_joining_and_bounded_offsets(dx):
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        pose = {'type': 'motion', 'dx': 0, 'dy': 0, 'keyDown': False, 'left': False, 'right': False}
        ws.send_json(pose)
        assert ws.receive_json()['code'] == 'not_joined'
        ws.send_json({'type': 'join', 'room': 'validation', 'nick': 'a'})
        ws.receive_json()
        ws.send_json({**pose, 'dx': dx})
        assert ws.receive_json()['code'] == 'bad_message'


def test_a_client_that_asks_for_packed_motion_gets_it_and_subscribes():
    manager.rooms.clear()
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as a, client.websocket_connect('/ws') as b:
            a.send_json({'type': 'join', 'room': 'packed', 'nick': 'a', 'motionVersion': 2})
            ja = a.receive_json()
            assert ja['motionVersion'] == 2
            # An older client in the same room is told nothing new.
            b.send_json({'type': 'join', 'room': 'packed', 'nick': 'b'})
            jb = b.receive_json()
            assert 'motionVersion' not in jb
            a.receive_json()  # b joined
            # Its subscription is ignored rather than refused.
            b.send_json({'type': 'motion_subscribe', 'ids': [ja['you']]})
            a.send_json({'type': 'motion_subscribe', 'ids': [jb['you']]})
            assert a.receive_json() == {'type': 'motion_snapshot', 'motions': [{'id': jb['you'], 'x': 0, 'y': 0, 'b': 0}]}
            b.send_json({'type': 'motion', 'dx': 2.5, 'dy': 0, 'keyDown': True, 'left': False, 'right': False})
            assert a.receive_json() == {'type': 'motion_edge', 'id': jb['you'], 'x': 10, 'b': 1}
            a.send_json({'type': 'pose', 'x': -4, 'b': 4})
            assert b.receive_json() == {'type': 'motion', 'id': ja['you'], 'dx': -1, 'dy': 0,
                                        'keyDown': False, 'left': False, 'right': True}


@pytest.mark.parametrize('message', [
    {'type': 'pose', 'x': 81}, {'type': 'pose', 'y': -81}, {'type': 'pose', 'x': 1.5}, {'type': 'pose', 'b': 8},
    {'type': 'motion_subscribe', 'ids': ['x'] * 21}, {'type': 'motion_subscribe', 'ids': ['']},
    {'type': 'join', 'room': 'validation', 'nick': 'a', 'motionVersion': 0},
])
def test_packed_motion_messages_are_bounded(message):
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        if message['type'] != 'join':
            ws.send_json({'type': 'join', 'room': 'validation', 'nick': 'a', 'motionVersion': 2})
            ws.receive_json()
        ws.send_json(message)
        assert ws.receive_json()['code'] == 'bad_message'


def test_a_newer_motion_version_gets_the_newest_this_server_has():
    manager.rooms.clear()
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        ws.send_json({'type': 'join', 'room': 'future', 'nick': 'a', 'motionVersion': 3})
        joined = ws.receive_json()
        assert joined['type'] == 'joined'
        assert joined['motionVersion'] == 2
