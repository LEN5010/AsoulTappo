# 架构 / Architecture

```
┌──────────────────── client/ (Tauri 2 + Vue 3 + TS) ─────────────────────┐        ┌──────── server/ (FastAPI) ────────┐
│  Rust (src-tauri)                  Webview: one overlay page (App.vue)  │        │ /ws  → RoomManager (in-memory)    │
│  rdev global hook ──"input"──────▶ own pet (PetView + CounterBar)       │◀──WS──▶│ /api/* → Game → SQLite            │
│  (kinds + mouse deltas only)       other members' pets (PetActor)       │  JSON  │ /packs → asset packs              │
│  hit-test thread ◀─"set_hit_regions"─ [data-hit] rects (hit.ts)         │◀─HTTP─▶│ /healthz, POST /rooms (+CORS)     │
│  tray / monitor / on-top           MainPanel (bag/dex/craft/room/set)   │        └───────────────────────────────────┘
│                                    TapBatcher(150ms) ─▶ RoomClient      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Why Tauri 2 + Vue (replacing PyQt6)
The original PyQt6 client (kept in `legacy/pyqt-client/`) was a ~1100-line `main.py` "god class" with manual QLabel geometry animation, Python-level global hooks and Windows-only dependencies. The new stack gives: a ~10 MB native shell using the system WebView2, GPU-composited CSS/DOM layers for the pet (trivial to scale and to render many small remote pets), a small Rust core for the OS integration, and a typed UI codebase.

## Desk overlay (one window)
The client has a single window, `main`: transparent, frameless, always-on-top, hidden from the taskbar, sized to the **work area** of one monitor (the monitor minus the taskbar). Everything lives in it: the own pet, the pets of everyone in the room and the floating panel. That is what lets you drag a friend's pet anywhere on your desktop.

The window must not block the desktop behind it, so mouse pass-through is decided per cursor position:

1. Every element that takes the mouse carries `data-hit` (pets, counter bar, chest bubble, toasts, panel). `hit.ts` collects their rectangles (CSS px) on `kick()` and every 200 ms, and sends them with `set_hit_regions` only when they changed.
2. A Rust thread (`spawn_hit_test`) polls `cursor_position()` every 30 ms, converts it to CSS px with `inner_position()` and `scale_factor()` (`hit.rs`, `HitState::interactive`), and calls `set_ignore_cursor_events` only when the answer flips.
3. While something is being dragged (`set_dragging(true)`) the window stays interactive even if the cursor leaves the rectangles. With click-through on, the window always ignores the mouse and the panel / counter bar are hidden.

The tray menu can show / hide the overlay, open the panel, toggle click-through, put the pet back to the bottom right, move the overlay to the next monitor, and quit.

## Client (`client/`)
**Rust (`src-tauri/`)**
- `input.rs` — global keyboard/mouse hook with [`rdev`](https://crates.io/crates/rdev) (Windows low-level hooks). `InputState` is a pure state machine (unit-tested): de-duplicates key auto-repeat, throttles mouse moves to ~60 Hz and emits only `key_down`, `key_up`, `mouse_down/up{button}`, `mouse_move{dx,dy}`. **Key identities are never forwarded**, not even to the webview.
- `hit.rs` — hit rectangles and the interactive / pass-through decision (unit-tested).
- `lib.rs` — commands `set_click_through`, `set_always_on_top`, `set_hit_regions`, `set_dragging`; fits the window to a monitor's work area; the hit-test thread; the tray menu.

**Frontend (`src/`)**
- `App.vue` — the overlay root. Places the own pet (`PetActor` + `PetView` + `CounterBar`), the other members' pets with name pills, drop toasts and the panel; decides whether emote bubbles grow to the left near the right screen edge.
- `pet/` — the pet and what floats around it:
  - `PetView.vue`: the ASoul-Little-Bun layers (bg, keyboard, mouse, left/right-click PNGs on the original 240×135 layout), a head accessory anchored per character, a desk accessory on the monitor, the emote bubble, the `+N` combo and the theme's like animation.
  - `PetActor.vue`: drag with pointer capture, reports position and size.
  - `EmotePlayer.ts`: one bubble per pet. A different emote swaps the picture, the same emote again shows `×N`, the bubble hides after the hold time (setting, 1.2–6 s). `TapCombo.ts` merges a member's tap batches into one rising `+N`.
  - `CounterBar.vue` (today / total counter, quick emotes, menu), `ChestBubble.vue`, `QuickEmote.vue`, `DropToast.vue`, `NamePill.vue`.
- `panel/` — `MainPanel.vue` (draggable floating panel, sidebar that folds) with five pages: 背包 (stage preview, 5 presets, 8 favorite emotes, owned items by kind), 图鉴 (everything grouped by rarity, locked items as silhouettes), 合成 (open chests, shards, craft a chosen item), 联机 (create / join / leave, members, tidy, remote pet size, names), 设置.
- `ui/` — design tokens (`tokens.css`) and shared pieces (`Icon`, `ItemArt`, `ItemCard`, `SegTabs`, `Modal`, `CharacterAvatar`).
- `items.ts` — one catalog of collectible items (`card:` / `emote:` / `acc:` / `theme:` ids, plus characters and decor for display) with ownership helpers.
- `stores/`
  - `settings.ts`: persisted settings, including the loadout (character, head, desk, theme, favorites) and pet / panel positions.
  - `player.ts`: progress, boxes, shards, crafting, loadout sync (local settings are the source of truth, mirrored to `POST /api/loadout` after 400 ms) and presets. Activity batches stay bound to their original server; responses from older server selections are ignored.
  - `room.ts`: room membership, per-member emote player and tap combo, remembers profile changes during reconnects.
  - `desk.ts`: where pets stand. Other members' positions are remembered per room by their stable member id (`uid`) in localStorage (10 rooms max); newcomers get the next free slot next to the own pet.
  - `counter.ts` (local tap counters), `pet.ts` (own pet input state), `ui.ts` (panel page and tabs), `theme.ts` (theme CSS variables).
- `net/` — `protocol.ts` (wire types), `TapBatcher.ts` (100–200 ms count batching), `RoomClient.ts` (WebSocket, ping/pong keepalive, exponential-backoff reconnect + automatic re-join), `api.ts` (HTTP API).
- `composables/tauri.ts` — Tauri event/command bridge; in a plain browser (`npm run dev`) it falls back to DOM key/mouse events and skips hit testing, so the UI can be developed without the shell.
- `characters.ts` — discovers characters from `src/assets/characters/<name>/*.png` (copied from the original project; see `COPYRIGHT.md` there) and holds the head anchor of each character.

## Server (`server/`)
- FastAPI app, one WebSocket endpoint, JSON messages validated by pydantic (`app/models.py`).
- `RoomManager` keeps rooms in a dict; max 20 peers per room; empty rooms are deleted; room IDs are `secrets.token_urlsafe(16)`.
- CORS middleware (`ASOULTAPPO_CORS_ORIGINS`, default `*`), `ping`→`pong` keepalive, `state` can change character, nickname, decor and accessories.
- Room state is **in memory, single process**. Scaling out would need Redis pub/sub or sticky routing.
- `app/game.py` holds the progression rules: activity credit, boxes, drops, shards and crafting, loadout and presets. Everything a player owns is one `items` table keyed by namespaced item id (`card:` / `emote:` / `acc:` / `theme:`). Older databases are migrated on startup (`cards` → `items`, `drops.card_id` → `item_id`).
- Activity batches use a session sequence for retry deduplication and a time-based credit balance; both commit with player progress.
- WebSocket profile / ownership checks run in a worker thread. Emotes are rate-limited (250 ms) and must be owned; ownership is cached per peer. Each peer serializes outgoing messages with a 2-second send deadline; failed peers are closed and removed.
- Room IDs are allocated on request, and Room objects are created on first join.

## Privacy / security notes
- Clients never send key contents or mouse positions; the Rust hook does not even expose key identity to the UI.
- The member id other people see (`uid`) is a hash of the player id and the room, so it differs per room and does not reveal the player token.
- Room ID is the only secret in v0; use `POST /rooms` for unguessable IDs. TODO: per-IP connection caps, optional room passphrase, origin checks.

## Deployment
`deploy/docker-compose.yml` runs the server behind Caddy (automatic HTTPS and WebSocket proxying). The client's server URL is configurable in the settings page (`https://` ⇒ `wss://`).

## CI (`.github/workflows/ci.yml`)
`server-tests` (pytest) · `client-web` (vitest + `vue-tsc` + `vite build`) · `client-tauri-windows` (`cargo check` + `cargo test` of `src-tauri` on `windows-latest`).

## Known gaps / open questions
- The overlay (work-area fitting, hit testing, DPI scaling, monitor switching) has not been tried on a real Windows desktop yet.
- Pass-through polls the cursor every 30 ms, so the first click right after the cursor enters a pet can land on the desktop behind it.
- Click-through can only be turned off from the tray menu.
- No installer/auto-update yet (Tauri NSIS bundle configured, updater not wired).
- macOS/Linux are not targets (transparent window + global hook behaviour untested).
