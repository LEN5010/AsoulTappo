# 架构 / Architecture (draft)

```
┌────────────── client/ (PyQt6, Windows) ───────────────┐        ┌──────── server/ (FastAPI) ────────┐
│ input_handler ──count──▶ net.TapBatcher ─▶ RoomClient │◀──WS──▶│ /ws  → RoomManager (in-memory)    │
│ main.py (pet UI) ◀── RoomEvents (tap/emote/state) ────│  JSON  │ /healthz, POST /rooms             │
└───────────────────────────────────────────────────────┘        └───────────────────────────────────┘
```

## Client (`client/`)
Imported from [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun) (GPL-2.0) as the starting point, with minimal changes. `client/net/` is a stub: `RoomClient` interface, `NullRoomClient` (offline), `TapBatcher` (count-only batching). Hook point: `InputHandler._on_key_press` / `_on_mouse_click`. Planned: render remote members' pets (small overlay windows or a strip beside the local pet), show emotes/tap bursts.

## Server (`server/`)
- FastAPI app, one WebSocket endpoint, JSON messages validated by pydantic (`app/models.py`).
- `RoomManager` keeps rooms in a dict; max 20 peers per room; empty rooms are deleted; room IDs are `secrets.token_urlsafe(16)`.
- State is **in memory, single process**. Scaling out would need Redis pub/sub or sticky routing — out of scope for MVP.
- No accounts, no persistence, no logging of content. Only tap *counts* are ever received.

## Privacy / security notes
- Clients never send key contents or mouse positions.
- Room ID is the only secret in v0; use `POST /rooms` for unguessable IDs. TODO: rate limiting, per-IP connection caps, optional room passphrase, origin checks.

## Deployment
`deploy/docker-compose.yml` runs the server behind Caddy (automatic HTTPS and WebSocket proxying).

## Open questions
- Whether to keep PyQt6 or move to another UI stack (to be evaluated; see roadmap).
- `client/update_checker.py` / `updater*.py` still point to the upstream repo's releases; they must be repointed or disabled before shipping builds.
