# 架构 / Architecture

```
┌──────────────────── client/ (Tauri 2 + Vue 3 + TS) ─────────────────────┐        ┌──────── server/ (FastAPI) ────────┐
│  Rust (src-tauri)                  Desk webview (App.vue)              │        │ /ws  → RoomManager (in-memory)    │
│  rdev global hook ──"input"──────▶ own pet (PetView + CounterBar)       │◀──WS──▶│ /api/* → Game → SQLite            │
│  (kinds + mouse deltas only)       other members' pets (PetActor)       │  JSON  │ /packs → asset packs              │
│  hit-test thread ◀─"set_hit_regions"─ [data-hit] rects (hit.ts)         │◀─HTTP─▶│ /healthz, POST /rooms (+CORS)     │
│  tray / monitor / on-top           Panel webview (PanelApp.vue)        │        └───────────────────────────────────┘
│                                    TapBatcher(150ms) ─▶ RoomClient      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Desk Overlay Window
The client has two independent windows. The transparent, frameless desk window (`main`) covers the monitor work area and renders the user's pet and room members' pets. The `alwaysOnTop` and click-through settings apply to this window.

The panel (`panel`) is a regular, resizable taskbar window, created on first open and reused after hiding. It uses normal application stacking, native dragging, and a minimize button. The tray and pet menu open it even while the desk is click-through. Closing the panel hides its window; the desk continues running.

`desktop/bridge.ts` mirrors player, collection, counter, and room state from the desk to the panel using targeted Tauri events. Panel actions run in the desk, which owns the room socket, activity reporting, and presence heartbeat. Settings sync as property patches in both directions. Both windows animate input, and the desk counts it once. Browser previews render the panel inside the desk.

Mouse pass-through is updated dynamically based on interactive regions:
1. Interactive desk elements carry `data-hit` (pets, counter bar, quick emote dock, chest bubble, toasts). `hit.ts` collects their bounding boxes and sends changes via `set_hit_regions`.
2. A Rust background thread (`spawn_hit_test`) checks the cursor position against the active hit regions and toggles `set_ignore_cursor_events`.
3. While dragging (`set_dragging(true)`), the overlay remains interactive until pointer release.

## Client (`client/`)
**Rust (`src-tauri/`)**
- `input.rs` — global keyboard/mouse hook using `rdev`, emitting `key_down`, `key_up`, `mouse_down/up{button}`, and `mouse_move{dx,dy}`.
- `hit.rs` — hit-region rectangle matching for cursor pass-through.
- `lib.rs` — desk interaction commands, independent panel window lifecycle, work-area sizing, and system tray menu.

**Frontend (`src/`)**
- `App.vue` — desk root placing the local pet, remote room members' pets, and drop toasts.
- `PanelApp.vue` — independent panel root, native open events, and input preview.
- `desktop/` — state mirroring and panel action requests to the desk.
- `pet/` — layered pet renderer (`PetView.vue`), drag actor (`PetActor.vue`), `CounterBar.vue`, single-row `QuickEmote.vue` dock, `EmoteBubble.vue`, `ComboBubble.vue`, `ChestBubble.vue`, `DropToast.vue`, and `NamePill.vue`.
- `panel/` — `MainPanel.vue` (sidebar, top bar, page shutter) with five pages:
  - `EmotesPage.vue`: pet stage, member cards (`MemberStrip.vue`, equipping the member's original skin), 8 favorite slots, and shelves of pet skins and owned emotes. The open-box button only jumps to the dex, which stays the single place that opens boxes.
  - `CollectionPage.vue`: emote dex. An album wall that opens onto each album's stickers; its footer is the main way to open boxes.
  - `CardsPage.vue`: one tab per card pool, with a draw view (`PoolStage.vue`, a card on stage plus a paged lineup of the whole pool) and an album view (`CardAlbum.vue`). Cards not owned yet are gray only in the album and the dex. Each pool wears the palette and stickers of its decoration set (`poolSkin` in `cards.ts`), applied by overriding the accent tokens on the page's subtree; the sidebar and frame keep the brand color. Custom properties resolve where they are declared, so a tinted subtree also carries `.ui-tint`, which re-declares the gradients from its own accent.
  - `OnlinePage.vue`: a live table of pets (`RoomStage.vue`), the room ticket, members and desk settings.
  - `SettingsPage.vue`.
- `panel/RevealScene.vue` — full-panel draw and box reveal, with `CardSpotlight.vue` for the card entrances and `reveal.ts` for their order. The scene covers the panel before the request goes out, because `drawCards` and `openBoxes` update the stores as soon as the response lands.
- `ui/` — design tokens (`tokens.css`), shared components (`Icon`, `SegTabs`, `FilterChips`, `Modal`, `ItemArt`, `CharacterAvatar`, `RangeInput`) and helpers (`motion.ts`, `focus.ts`, `palette.ts`). `Modal` and `RevealScene` teleport to `.panel-overlay` and carry `data-overlay`, which keeps Esc from closing the panel underneath them.
- `stores/` — reactive state for `settings`, `player`, `room`, `desk`, `counter`, `pet`, `ui`, and `theme`.
- Member support colors follow the catalog: 嘉然 `#E799B0`, 乃琳 `#576690`, 贝拉 `#DB7D74`, 心宜 `#C93773`, 思诺 `#7252C0`. Theme accents retain those colors; sidebar and member selection surfaces mix in white, while small colored text uses a deeper tone for contrast.
- `net/` — `protocol.ts`, `TapBatcher.ts`, `RoomClient.ts`, and `api.ts`.

## Server (`server/`)
- `app/main.py` — FastAPI application serving `/ws` for real-time rooms, `/api/*` for progression/collection/draws, and `/packs` for static asset packs.
- `app/rooms.py` — in-memory room management (up to 20 members per room).
- `app/game.py` & `app/store.py` — SQLite-backed player progression, activity credit, emote chests, shard crafting, online-time card draw tickets, and 400-draw shared pity.
