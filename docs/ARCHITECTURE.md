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
1. Interactive desk elements carry `data-hit` (pets, counter bar, quick emote dock, resonance bubble). `hit.ts` collects their bounding boxes and sends changes via `set_hit_regions`.
2. A Rust background thread (`spawn_hit_test`) checks the cursor position against the active hit regions and toggles `set_ignore_cursor_events`.
3. While dragging (`set_dragging(true)`), the overlay remains interactive until pointer release.

## Client (`client/`)
**Rust (`src-tauri/`)**
- `input.rs` — global keyboard/mouse hook using `rdev`, emitting `key_down`, `key_up`, `mouse_down/up{button}`, and `mouse_move{dx,dy}`.
- `hit.rs` — hit-region rectangle matching for cursor pass-through.
- `lib.rs` — desk interaction commands, independent panel window lifecycle, work-area sizing, and system tray menu.

**Frontend (`src/`)**
- `App.vue` — desk root placing the local pet, remote room members' pets, and the resonance shortcut.
- `PanelApp.vue` — independent panel root, native open events, and input preview.
- `desktop/` — state mirroring and panel action requests to the desk.
- `pet/` — layered pet renderer (`PetView.vue`), drag actor (`PetActor.vue`), `CounterBar.vue`, single-row `QuickEmote.vue` dock, `EmoteBubble.vue`, `ComboBubble.vue`, and `NamePill.vue`.
- `panel/` — `MainPanel.vue` (sidebar, top bar, page shutter) with five pages:
  - `EmotesPage.vue`: backpack with original members, owned skins, owned emotes and eight favorite slots. Its resource bar links to resonance.
  - `ResonancePage.vue`: one all-member pool, card/skin stage (`PoolStage.vue`), tier counts, independent shared pity counters, income and single/ten/all draws. The pool includes all 428 non-starter collectibles once.
  - `CollectionPage.vue`: dex with card, emote and skin categories. Cards retain series filters and the album/detail views; emotes retain the searchable album wall. Missing common cards/emotes and rare emotes can be crafted. Locked skins link to resonance.
  - `OnlinePage.vue`: a live table of pets (`RoomStage.vue`), the room ticket, members and desk settings.
  - `SettingsPage.vue`.
- `panel/RevealScene.vue` — mixed resonance results, with `CardSpotlight.vue` for cards (including dancing videos), `SkinSpotlight.vue` for skins, and `reveal.ts` for rarity ordering and grouped duplicates. The scene covers the panel before `resonate` updates the stores. Single emotes go directly to the summary; batches spotlight legendary, skin and epic drops.
- `resonance.ts` — pure client pool construction and effective rates. The server constructs the same pools from manifest v4, with shared cards retaining one item id in the unified pool.
- `ui/` — design tokens (`tokens.css`), shared components (`Icon`, `SegTabs`, `FilterChips`, `Modal`, `ItemArt`, `CharacterAvatar`, `RangeInput`) and helpers (`motion.ts`, `focus.ts`, `palette.ts`). `Modal` and `RevealScene` teleport to `.panel-overlay` and carry `data-overlay`, which keeps Esc from closing the panel underneath them.
- `stores/` — reactive state for `settings`, `player`, `room`, `desk`, `counter`, `pet`, `ui`, and `theme`.
- Member support colors follow the catalog: 嘉然 `#E799B0`, 乃琳 `#576690`, 贝拉 `#DB7D74`, 心宜 `#C93773`, 思诺 `#7252C0`. Theme accents retain those colors; sidebar and member selection surfaces mix in white, while small colored text uses a deeper tone for contrast.
- `net/` — `protocol.ts`, `TapBatcher.ts`, `RoomClient.ts`, and `api.ts`.

## Server (`server/`)
- `app/main.py` — FastAPI application serving `/ws` for real-time rooms, `/api/*` for progression/collection/draws, and `/packs` for static asset packs.
- `app/rooms.py` — in-memory room management (up to 20 members per room).
- `app/game.py` & `app/store.py` — SQLite-backed progression, rate-limited activity, fractional online shard income, resonance and crafting. Each draw costs 160 shards; independent legendary (400) and skin (200) pity counters advance independently in the unified pool. All higher tiers prefer unowned items and their completed weights move to common. Only completed common pools produce duplicates (+40 shards). First startup migrates old balances once, preserving items and legendary pity; new players receive 1600 shards.
