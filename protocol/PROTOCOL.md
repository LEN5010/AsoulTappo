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
| `state` | `character` (≤32) and/or `nick` (≤24); at least one | update own profile (broadcast to the room) |
| `ping` | – | keepalive; the server answers `pong` (allowed before `join`). Clients send one every ~20s and reconnect when no `pong` arrives |

## Server → Client
| type | fields |
|---|---|
| `joined` | `room`, `you` (your member id), `members[]` (`id`,`nick`,`character`,`taps`) |
| `member_joined` | `member` |
| `member_left` | `id` |
| `tap` | `id`, `count`, `total` — broadcast to everyone in the room, including the sender |
| `emote` | `id`, `emote` — broadcast to everyone, including the sender |
| `state` | `id`, `character`, `nick` — full current profile of that member, broadcast to everyone, including the sender |
| `pong` | – |
| `error` | `code`, `message` |

Error codes: `room_full`, `bad_message`, `not_joined`, `already_joined`.

## Example
```json
→ {"type":"join","room":"Zk3...","nick":"小面包","character":"嘉然"}
← {"type":"joined","room":"Zk3...","you":"a1b2c3d4","members":[{"id":"a1b2c3d4","nick":"小面包","character":"嘉然","taps":0}]}
→ {"type":"tap","count":7}
← {"type":"tap","id":"a1b2c3d4","count":7,"total":7}
```

Reference models: `server/app/models.py` (server, pydantic) and `client/src/net/protocol.ts` (client, TypeScript).

## Client behaviour (reference implementation: `client/src/net/`)
- **Tap batching:** the client counts key presses / mouse clicks locally and sends one `tap` with the summed count every 100–200 ms (default 150 ms) while there is anything pending (`TapBatcher`). Counts above 500 are split.
- **Reconnect:** on disconnect the client retries with exponential backoff (0.5 s → 15 s, plus jitter) and re-sends `join` for the last room (member id changes after a reconnect). `room_full` is final and stops retrying.
- **Own events:** `tap`/`emote`/`state` are echoed to the sender; the client has already animated locally and ignores the echo except for updating totals/profile.

HTTP: the server enables CORS (`ASOULTAPPO_CORS_ORIGINS`, default `*`) so the Tauri webview / browser can call `POST /rooms`. The protocol is unversioned/unstable until MVP phase 2.
