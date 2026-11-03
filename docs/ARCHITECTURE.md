# 架构 / Architecture

```
┌──────────────── client/ (Tauri 2 + Vue 3 + TS) ────────────────┐         ┌──────── server/ (FastAPI) ───────┐
│  Rust (src-tauri)                 Webview (Vue)                │         │ /ws  → RoomManager (in-memory)   │
│  rdev global hook ──"input"──▶ App.vue ─▶ PetView (layers)     │◀──WS───▶│ /healthz, POST /rooms (+CORS)    │
│  (kinds + mouse deltas only)         │ registerTap()           │  JSON   └──────────────────────────────────┘
│  tray / click-through / on-top       ▼                         │
│  window resize commands        TapBatcher(150ms) ─▶ RoomClient │
└────────────────────────────────────────────────────────────────┘
```

## Why Tauri 2 + Vue (replacing PyQt6)
The original PyQt6 client (kept in `legacy/pyqt-client/`) was a ~1100-line `main.py` "god class" with manual QLabel geometry animation, Python-level global hooks and Windows-only dependencies. The new stack gives: a ~10 MB native shell using the system WebView2, GPU-composited CSS/DOM layers for the pet (trivial to scale and to render many small remote pets), a small Rust core for the OS integration, and a typed UI codebase.

## Client (`client/`)
**Rust (`src-tauri/`)**
- `input.rs` — global keyboard/mouse hook with [`rdev`](https://crates.io/crates/rdev) (Windows low-level hooks). `InputState` is a pure state machine (unit-tested): de-duplicates key auto-repeat, throttles mouse moves to ~60 Hz and emits only `key_down`, `key_up`, `mouse_down/up{button}`, `mouse_move{dx,dy}`. **Key identities are never forwarded**, not even to the webview.
- `lib.rs` — window commands (`set_click_through`, `set_always_on_top`, `resize_window`, `reset_position`), system tray (show/hide, panel, click-through toggle, reset position, quit).
- `tauri.conf.json` — the single `main` window is transparent, frameless, always-on-top, non-resizable (resized to its content by the frontend).

**Frontend (`src/`)**
- `components/PetView.vue` — layered pet (bg, keyboard, mouse, left/right-click PNGs on the original 240×135 layout). Keyboard layer presses/bounces on key events, mouse layer follows (smoothed, clamped) mouse deltas, click images show while pressed. Remote pets reuse it at small scale; they bounce per tap batch and show `+N` bursts and emotes.
- `net/` — `protocol.ts` (wire types), `TapBatcher.ts` (100–200 ms count batching), `RoomClient.ts` (WebSocket, ping/pong keepalive, exponential-backoff reconnect + automatic re-join).
- `stores/` — `settings.ts` persists applied settings; `room.ts` manages room membership and remembers profile changes during reconnects. `player.ts` keeps activity batches bound to their original server and ignores responses from prior server selections.
- `MouseMotion.ts` starts animation on input, settles small offsets to zero, and stops scheduling frames while idle. Pet layers animate with transforms.
- `composables/tauri.ts` — Tauri event/command bridge; in a plain browser (`npm run dev`) it falls back to DOM key/mouse events so the UI can be developed without the shell.
- `characters.ts` — discovers characters from `src/assets/characters/<name>/*.png` (copied from the original project; see `COPYRIGHT.md` there).

## Server (`server/`)
- FastAPI app, one WebSocket endpoint, JSON messages validated by pydantic (`app/models.py`).
- `RoomManager` keeps rooms in a dict; max 20 peers per room; empty rooms are deleted; room IDs are `secrets.token_urlsafe(16)`.
- CORS middleware (`ASOULTAPPO_CORS_ORIGINS`, default `*`), `ping`→`pong` keepalive, `state` can change character and nickname.
- State is **in memory, single process**. Scaling out would need Redis pub/sub or sticky routing — out of scope for MVP.
- Player progress and collections persist in SQLite. Activity batches use a session sequence for retry deduplication and a time-based credit balance; both commit with player progress.
- WebSocket decoration reads/writes run in a worker thread. Each peer serializes outgoing messages with a 2-second send deadline; failed peers are closed and removed.
- Room IDs are allocated on request, and Room objects are created on first join.

## Privacy / security notes
- Clients never send key contents or mouse positions; the Rust hook does not even expose key identity to the UI.
- Room ID is the only secret in v0; use `POST /rooms` for unguessable IDs. TODO: rate limiting, per-IP connection caps, optional room passphrase, origin checks.

## Deployment
`deploy/docker-compose.yml` runs the server behind Caddy (automatic HTTPS and WebSocket proxying). The client's server URL is configurable in the settings panel (`https://` ⇒ `wss://`).

## CI (`.github/workflows/ci.yml`)
`server-tests` (pytest) · `client-web` (vitest + `vue-tsc` + `vite build`) · `client-tauri-windows` (`cargo check` + `cargo test` of `src-tauri` on `windows-latest`).

## Known gaps / open questions
- Pet window geometry is auto-sized to content via a `ResizeObserver`; multi-monitor / DPI edge cases untested.
- Click-through can only be turned off from the tray menu.
- No installer/auto-update yet (Tauri NSIS bundle configured, updater not wired).
- macOS/Linux are not targets (transparent window + global hook behaviour untested).
