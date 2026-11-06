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

`desktop/bridge.ts` mirrors player, collection, counter, and room state from the desk to the panel using targeted Tauri events. Panel actions run in the desk, which owns the room socket, activity reporting, and presence heartbeat. Settings sync as property patches in both directions. The panel subscribes to independent player, collection, counter, and room-profile slices while visible. Only the room page subscribes to member runtime updates, coalesced per changed member every 50ms. Hiding or minimizing the panel stops those subscriptions and preview input, and keeps an in-progress resonance reveal; reopening refreshes all state slices and continues that reveal. KeepAlive pages pause their videos and automatic scrolling when deactivated. The desk counts input once and continues room networking and income reporting. Browser previews render the panel inside the desk.

Mouse pass-through is updated dynamically based on interactive regions:
1. Interactive desk elements carry `data-hit` (pets, counter bar, quick emote dock, resonance bubble). `hit.ts` observes hit-target size, position, insertion and removal, collects bounding boxes when layout changes, and sends them via `set_hit_regions`. Geometry animations sample frames only during playback.
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
  - `EmotesPage.vue`: backpack with a fixed showcase (the pet stage beside eight favorite slots and the wallet), one filter bar (`MemberStrip.vue`, kind tabs, search) and scrolling shelves of all skins (locked ones dimmed and disabled) and owned emotes. Only the shelves scroll, so the slots stay in reach while dragging. The wallet links to resonance.
  - `ResonancePage.vue`: one all-member pool with a self-rotating banner of its 36 dynamic cards, a separate row of skins that open their details, tier counts (`PoolStage.vue`), independent shared pity counters, income and single/ten/all draws. The pool includes all 550 non-starter collectibles once.
  - `CollectionPage.vue`: dex with card, emote and skin categories. Cards retain series filters and the album/detail views; emotes retain the searchable album wall. Eligible missing cards and emotes are crafted directly in their details, with balance, pending and success states. Skins use portrait cards, member colors, ownership filters, a live pet preview and an equip action. Locked skins link to resonance.
  - `OnlinePage.vue`: a table of live pets (`RoomStage.vue`), six to a row, that opens another row whenever the room fills one, up to `MAX_ROOM_SIZE`; the room ticket, desk settings and the member list.
  - `SettingsPage.vue`: a profile strip with the nickname and totals, theme cards showing each member on her theme's gradient, then the pet, window and server groups in two columns.
- Album tabs include all series together. Unowned cards retain color with reduced brightness; up to three visible owned videos loop; all unowned cards, including dancing cards, show static posters. Offscreen album videos release their source. The resonance stage and its detail modal use a preview mode: all dynamic cards play at normal brightness regardless of ownership. Card videos are bundled under `public/assets/cards/<series>/*.mp4` and referenced through `bundle:` URLs. All 36 clips retain their complete duration and audio, using H.264 at 640 pixels wide / 30 fps and AAC 48 kbps. The server packs contain full-resolution static artwork and theme resources.
- `panel/RevealScene.vue` — mixed resonance results, with `CardSpotlight.vue` for cards (including dancing videos), `SkinSpotlight.vue` for skins, and `reveal.ts` for rarity ordering, grouped duplicates and fast-forwarding ordinary results. Dynamic cards use their bundled thumbnail during the entrance, so video reveals do not wait for a remote poster. The scene covers the panel before `resonate` updates the stores. Results play in draw order. Skipping fast-forwards ordinary cards, dancing cards and emotes, then pauses for each hidden-card or skin reveal. This mode carries across batches.
- `resonance.ts` — pure client pool construction and effective rates. The server constructs the same pools from manifest v4, with shared cards retaining one item id in the unified pool.
- `ui/` — design tokens (`tokens.css`), shared components (`Icon`, `SegTabs`, `FilterChips`, `Modal`, `ItemArt`, `CharacterAvatar`, `RangeInput`) and helpers (`motion.ts`, `focus.ts`, `palette.ts`). `Modal` and `RevealScene` teleport to `.panel-overlay` and carry `data-overlay`, which keeps Esc from closing the panel underneath them.
- `stores/` — reactive state for `settings`, `player`, `room`, `desk`, `counter`, `pet`, `ui`, and `theme`.
- Member support colors follow the catalog: 嘉然 `#E799B0`, 乃琳 `#576690`, 贝拉 `#DB7D74`, 心宜 `#C93773`, 思诺 `#7252C0`. Theme accents are tuned from those colors in `stores/theme.ts`, and each theme picks two neighboring hues for its gradients; small colored text uses a deeper tone for contrast.
- `net/` — `protocol.ts`, `TapBatcher.ts`, `MotionSender.ts`, `RoomClient.ts`, and `api.ts`. MotionSender coalesces bounded pet-layer offsets at 20Hz, sends button edges immediately and clears queued movement on disconnect. Remote pets interpolate mouse movement and hold short presses for 70ms so edges remain visible. The server sends continuous motion as one room batch every 50ms, with immediate ordered button edges. Each peer has its own writer; adjacent queued position batches merge to their newest values, while reliable events retain order. Send timeout and an outbox limit of 256 messages remove stalled receivers.

## Server (`server/`)
- `app/main.py` — FastAPI application serving `/ws` for real-time rooms, `/api/*` for progression/collection/draws, and `/packs` for static asset packs.
- `app/rooms.py` — in-memory room management (up to 20 members per room), room motion batching and per-connection writers.
- `app/game.py` & `app/store.py` — SQLite-backed progression, rate-limited activity, fractional online shard income, resonance and crafting. Each draw costs 160 shards; independent legendary (400) and skin (200) pity counters advance independently in the unified pool. All higher tiers prefer unowned items and their completed weights move to common. The uncommon emote tier has 6% odds, taken from rare (now 3%) and ordinary emotes. Common draws use card/emote weights 45 : 40.5, then prefer unowned items within that kind. Completed kinds produce duplicates; only emotes refund 10 shards, while cards increment their owned count. First startup migrates old balances once, preserving items and legendary pity; new players receive 1600 shards.

## Rendering and persistence costs

- Backpack and dex sticker grids mount the visible rows plus two rows of overscan on each side. Dynamic emotes use static 160px covers in lists and favorite slots, and play their original animation when previewed or sent. Generated covers carry `thumb` and `animated` in the asset manifest.
- Pet backgrounds have 480px and 960px variants selected by displayed scale. Small avatars use a separate 264×224 crop. `scripts/build_previews.py` rebuilds these files from the bundled originals and is also called by the main asset pipeline.
- Pool skin scrolling caches dimensions through ResizeObserver and cancels its animation frame while paused, off-page or hidden. The room table applies its contour to the static background layer.
- Resonance maintains missing-item pools incrementally during each transaction. Repeated item gains merge into one increment per item; drop history uses a single executemany call. Status and presence count collectible rows in SQLite instead of loading the full ownership map. SQLite remains the persistence backend.
