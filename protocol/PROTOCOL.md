# AsoulTappo 协议 / Protocol (v0, draft)

Transport: WebSocket, endpoint `/ws`, one JSON object per text frame.
HTTP helpers: `GET /healthz` → `{"status":"ok","rooms":N}`, `POST /rooms` → `{"room":"<random id>"}`.

## 隐私原则 / Privacy
**只发送点击次数,绝不发送按键内容**(不上传按了哪个键、输入了什么、鼠标坐标)。
Only tap *counts* are sent. Key identities, typed text and mouse positions never leave the client.

## Rooms
- Room ID: client-chosen string (1–64 chars) or a server-generated random URL-safe ID (~128 bit, from `POST /rooms`). Long random IDs are the only access control in v0.
- Max **20** members per room. Rooms are created on first join and dropped when empty.

## Client → Server
| type | fields | notes |
|---|---|---|
| `join` | `room`, `nick` (≤24), `character` (≤32, default `"default"`) | must be the first message |
| `leave` | – | leave the room (connection may stay open) |
| `tap` | `count` (1–500) | **batched** count since last message; send ≤ ~4×/s |
| `emote` | `emote` (≤32) | emote key, e.g. `"heart"` |
| `state` | `character` (≤32) | switch displayed character |

## Server → Client
| type | fields |
|---|---|
| `joined` | `room`, `you` (your member id), `members[]` (`id`,`nick`,`character`,`taps`) |
| `member_joined` | `member` |
| `member_left` | `id` |
| `tap` | `id`, `count`, `total` — broadcast to everyone in the room, including the sender |
| `emote` | `id`, `emote` — broadcast to everyone, including the sender |
| `state` | `id`, `character` — broadcast to everyone, including the sender |
| `error` | `code`, `message` |

Error codes: `room_full`, `bad_message`, `not_joined`, `already_joined`.

## Example
```json
→ {"type":"join","room":"Zk3...","nick":"小面包","character":"嘉然"}
← {"type":"joined","room":"Zk3...","you":"a1b2c3d4","members":[{"id":"a1b2c3d4","nick":"小面包","character":"嘉然","taps":0}]}
→ {"type":"tap","count":7}
← {"type":"tap","id":"a1b2c3d4","count":7,"total":7}
```

Reference models: `server/app/models.py`. The protocol is unversioned/unstable until MVP phase 2.
