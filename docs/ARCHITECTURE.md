# 架构 / Architecture

```
┌──────────────────── client/ (Tauri 2 + Vue 3 + TS) ─────────────────────┐        ┌──────── server/ (FastAPI) ────────┐
│  Rust (src-tauri)                  Webview: one overlay page (App.vue)  │        │ /ws  → RoomManager (in-memory)    │
│  rdev global hook ──"input"──────▶ own pet (PetView + CounterBar)       │◀──WS──▶│ /api/* → Game → SQLite            │
│  (kinds + mouse deltas only)       other members' pets (PetActor)       │  JSON  │ /packs → asset packs              │
│  hit-test thread ◀─"set_hit_regions"─ [data-hit] rects (hit.ts)         │◀─HTTP─▶│ /healthz, POST /rooms (+CORS)     │
│  tray / monitor / on-top           MainPanel (emotes/dex/room/settings) │        └───────────────────────────────────┘
│                                    TapBatcher(150ms) ─▶ RoomClient      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Desk Overlay Window
The client uses a single transparent, frameless, always-on-top window (`main`) sized to the monitor work area. It renders the user's own pet, room members' pets, and the floating panel.

Mouse pass-through is updated dynamically based on interactive regions:
1. Interactive elements carry `data-hit` (pets, counter bar, quick emote dock, chest bubble, toasts, panel). `hit.ts` collects their bounding boxes and sends changes via `set_hit_regions`.
2. A Rust background thread (`spawn_hit_test`) checks the cursor position against the active hit regions and toggles `set_ignore_cursor_events`.
3. While dragging (`set_dragging(true)`), the overlay remains interactive until pointer release.

## Client (`client/`)
**Rust (`src-tauri/`)**
- `input.rs` — global keyboard/mouse hook using `rdev`, emitting `key_down`, `key_up`, `mouse_down/up{button}`, and `mouse_move{dx,dy}`.
- `hit.rs` — hit-region rectangle matching for cursor pass-through.
- `lib.rs` — Tauri commands (`set_click_through`, `set_always_on_top`, `set_hit_regions`, `set_dragging`), work-area sizing, and system tray menu.

**Frontend (`src/`)**
- `App.vue` — overlay root placing the local pet, remote room members' pets, drop toasts, and `MainPanel`.
- `pet/` — layered pet renderer (`PetView.vue`), drag actor (`PetActor.vue`), `CounterBar.vue`, single-row `QuickEmote.vue` dock, `EmoteBubble.vue`, `ComboBubble.vue`, `ChestBubble.vue`, `DropToast.vue`, and `NamePill.vue`.
- `panel/` — `MainPanel.vue` (sidebar, top bar, page shutter) with five pages:
  - `EmotesPage.vue`: pet stage, 8 favorite slots, and the owned emotes and pet skins.
  - `CollectionPage.vue`: emote dex. An album wall that opens onto each album's stickers; its footer is the main way to open boxes.
  - `CardsPage.vue`: one tab per card pool, with a draw view (`PoolStage.vue`) and an album view (`CardAlbum.vue`). Each pool wears the palette and stickers of its decoration set (`poolSkin` in `cards.ts`), applied by overriding the accent tokens on the page's subtree; the sidebar and frame keep the brand color.
  - `OnlinePage.vue`: a live table of pets (`RoomStage.vue`), the room ticket, members and desk settings.
  - `SettingsPage.vue`.
- `panel/RevealScene.vue` — full-panel draw and box reveal, with `CardSpotlight.vue` for the card entrances and `reveal.ts` for their order. The scene covers the panel before the request goes out, because `drawCards` and `openBoxes` update the stores as soon as the response lands.
- `ui/` — design tokens (`tokens.css`), shared components (`Icon`, `SegTabs`, `FilterChips`, `Modal`, `ItemArt`, `CharacterAvatar`, `RangeInput`) and helpers (`motion.ts`, `focus.ts`, `palette.ts`). `Modal` and `RevealScene` teleport to `.panel-overlay` and carry `data-overlay`, which keeps Esc from closing the panel underneath them.
- `stores/` — reactive state for `settings`, `player`, `room`, `desk`, `counter`, `pet`, `ui`, and `theme`.
- `net/` — `protocol.ts`, `TapBatcher.ts`, `RoomClient.ts`, and `api.ts`.

## Server (`server/`)
- `app/main.py` — FastAPI application serving `/ws` for real-time rooms, `/api/*` for progression/collection/draws, and `/packs` for static asset packs.
- `app/rooms.py` — in-memory room management (up to 20 members per room).
- `app/game.py` & `app/store.py` — SQLite-backed player progression, activity credit, emote chests, shard crafting, online-time card draw tickets, and 400-draw shared pity.
