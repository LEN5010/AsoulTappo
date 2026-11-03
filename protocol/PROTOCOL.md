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
| `join` | `room`, `nick` (≤24), `character` (≤32, default `"default"`), optional `token` (16–128 chars) | must be the first message. With a `token` the server looks up the player's `frame` / `badge` / `head` / `desk` and gives the member a stable per-room `uid`; without one they are all `null` |
| `leave` | – | leave the room (connection may stay open) |
| `tap` | `count` (1–500) | **batched** count since last message; send ≤ ~4×/s |
| `emote` | `emote` (≤32) | emote key: a legacy glyph key (`"heart"`), `"thumbup"` (the theme's animated like), or `<emoteSetId>.<nn>` from the manifest (e.g. `jiaran-eat.03`). Glyph keys, `thumbup` and the starter emotes are free; other emotes must be owned by the player (`token`), otherwise `locked`. At most one emote per 250 ms, otherwise `rate_limited` |
| `state` | `character` (≤32), `nick` (≤24), `frame`, `badge` (≤32), `head`, `desk` (≤48); at least one | update own profile (broadcast to the room). Decor and accessories need a `token` on join; decor must be unlocked (`locked` / `bad_decor`), accessories owned and in the right slot (`locked` / `bad_item`). `""` clears a field |
| `ping` | – | keepalive; the server answers `pong` (allowed before `join`). Clients send one every ~20s and reconnect when no `pong` arrives |

## Server → Client
| type | fields |
|---|---|
| `joined` | `room`, `you` (your member id), `members[]` (`id`,`uid`,`nick`,`character`,`taps`,`frame`,`badge`,`head`,`desk`) |
| `member_joined` | `member` |
| `member_left` | `id` |
| `tap` | `id`, `count`, `total` — broadcast to everyone in the room, including the sender |
| `emote` | `id`, `emote` — broadcast to everyone, including the sender |
| `state` | `id`, `character`, `nick`, `frame`, `badge`, `head`, `desk` — full current profile of that member, broadcast to everyone, including the sender |
| `pong` | – |
| `error` | `code`, `message` |

Error codes: `room_full`, `bad_message`, `not_joined`, `already_joined`, `locked` (decor / accessory / emote not owned), `bad_decor` (unknown frame/badge id), `bad_item` (unknown accessory or wrong slot), `rate_limited` (emotes sent too fast).

`id` changes on every (re)connect. `uid` is `sha256("<player id>:<room>")[:10]`: the same for a player every time they join that room, different between rooms, and `null` for members without a token. The reference client uses it to remember where you dragged someone's pet.

## HTTP API (progression)
Identity is a random secret the client generates once and sends as the `X-Player-Token` header (16–128 chars); the server stores only a hash (`player_id = sha256(token)[:16]`). Anyone holding the token is that player — there are no accounts and no payments.

| route | notes |
|---|---|
| `GET /api/manifest` | asset / card / theme metadata (same as `assets-packs/manifest.json`) |
| `GET /api/me` | status: unopened `boxes`, `shards`, `progress` (`taps`, `tapsPerBox`, `minutes`, `minutesPerBox`), `boxesToday` / `dailyCap`, `totals` (`taps`, `activeMinutes`, `opened`, `owned`, `items` = number of droppable items), `pity`, `unlocked` decor, selected `frame` / `badge` |
| `POST /api/activity` `{taps, session, sequence}` | report a batch of tap counts. `session` is a random 16–128 character ID per reporter; `sequence` starts at 1 and increases for each new batch. Retries reuse the same batch and sequence. Credit accrues at 15 taps/s of actual elapsed time, with fractional credit retained and a maximum balance of 120 seconds (≤ 5000 taps per report). A minute is "active" once it has ≥ 10 taps. A box is earned per 600 credited taps or per 10 active minutes; ≤ 10 boxes/day, ≤ 20 unopened |
| `POST /api/boxes/open` `{count?}` | open `count` boxes (default 1, at most 10 per request and at most the boxes you have). Each box rolls an item with rarity weights 70/22/7/1, soft pity (epic weight +8 per open beyond 10 without epic+), hard pity (epic+ at 20, legendary at 60); unowned items weigh 3×. Returns the status plus `drops[]` (`item`, `rarity`, `new`, `count`, `shards`). A duplicate gives shards: common 1 / rare 3 / epic 8 / legendary 20 |
| `POST /api/craft` `{item}` | spend shards on one missing item: common 10 / rare 30 / epic 80 / legendary 200. Returns the status plus `item`. Starter items can't be crafted |
| `GET /api/collection` | `owned` (`item id → count`) and `recent` drops (`item`, `rarity`, `new`, `ts`) |
| `GET /api/loadout` | `character`, `head`, `desk`, `theme`, `favorites` (≤8 emote keys), `frame`, `badge` |
| `POST /api/loadout` | change part of the loadout (only the keys you send). Everything must be owned / unlocked; `""` clears `head` / `desk` / `frame` / `badge`. Returns the full loadout |
| `GET /api/presets` | `presets`: 5 slots, each `null` or `{name, loadout}` |
| `POST /api/presets/{slot}` `{loadout, name?}` | save a loadout in slot 0–4 (validated like `POST /api/loadout`); `loadout: null` clears the slot. Returns all presets |
| `POST /api/decor` `{frame?, badge?}` | choose avatar frame / badge (must be unlocked) |
| `GET /packs/index.json`, `/packs/...` | downloadable asset packs with sizes and sha256 |

Errors are `{"detail": {"code", "message"}}`. Status 401: `bad_token`. Status 409: `no_box`, `no_shards`, `owned`. Status 400: `locked`, `bad_decor`, `bad_item`, `bad_slot`.

### Items
Everything a player can own has a namespaced id: `card:<card id>`, `emote:<emote key>`, `acc:<accessory id>`, `theme:<theme id>`. Rarities come from the manifest (`cards[].rarity`, `emoteSets[].rarity`, `accessories[].rarity`, `themes[].rarity`). Items in `manifest.starter` (the first 4 emotes of each character's first set and the default theme) are owned by everyone and never drop. Accessories have a slot: `head` (riders and figures sit on the pet's head) or `desk` (animations stand on the monitor).

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
- **Emotes:** the client only offers emotes the player owns and sends at most one every 400 ms. After (re)joining it re-sends `head` / `desk` when they differ from what the server reported in `joined`.

HTTP: the server enables CORS (`ASOULTAPPO_CORS_ORIGINS`, default `*`) so the Tauri webview / browser can call `POST /rooms`. The protocol is unversioned/unstable until MVP phase 2.

## Activity and server switching

- Call `GET /api/me` when starting input reporting to establish the counting baseline. The first 20-second batch then receives its actual elapsed-time allowance.
- Activity progress, remaining rate credit and the session sequence commit in one SQLite transaction. Replayed sequences return current status with `credited: 0` and `newBoxes: 0`.
- The client retains a failed batch separately from newly accumulated taps and retries the original `session` / `sequence`. HTTP requests time out after 10 seconds.
- Editing the server field changes a draft. Applying it leaves the old room, switches the progress and asset server, and clears displayed player state. Pending activity retains its original destination; responses from older server selections are ignored.
- `POST /rooms` generates an ID; the room is allocated when its first member joins. Sends to a member have a 2-second deadline; failed members are removed and closed with code 1013.

## Upgrade

Update the server and client together.

- 0.3: boxes drop all item kinds, not only cards, and duplicates give shards. On startup the server adds the `shards` / `loadout` player columns and the `presets` table, copies `cards` into `items` (ids get the `card:` prefix) and renames `drops.card_id` to `item_id`. Older clients can't read the new `drops` / `owned` shapes.
- Activity requests require `session` and `sequence`. On server startup the existing schema initialization creates `activity_budget` and `activity_sessions` alongside the player tables. Existing player progress and collections remain available.
