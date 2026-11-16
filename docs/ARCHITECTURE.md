# 架构 / Architecture

```
┌──────────────────── client/ (Tauri 2 + Vue 3 + TS) ─────────────────────┐        ┌──────── server/ (FastAPI) ────────┐
│  Rust (src-tauri)                  Desk webview (App.vue)              │        │ /ws  → RoomManager (in-memory)    │
│  input hook ──"input"────────────▶ own pet (PetView + CounterBar)       │◀──WS──▶│ /api/* → Game → SQLite            │
│  (kinds + mouse deltas only)       other members' pets (PetActor)       │  JSON  │ /packs → asset packs              │
│  hit-test thread ◀─"set_hit_regions"─ [data-hit] rects (hit.ts)         │◀─HTTP─▶│ /healthz, POST /rooms (+CORS)     │
│  tray / monitor / on-top           Panel webview (PanelApp.vue)        │        └───────────────────────────────────┘
│                                    TapBatcher(150ms) ─▶ RoomClient      │
└─────────────────────────────────────────────────────────────────────────┘
```

Rules of play (rates, prices, limits) live in the server's economy file and reach the client through `/api/economy`;
the catalog (cards, emotes, skins, series) lives in `assets-packs/manifest.json`. This page names neither's values.

## Windows

The client runs up to four windows. Each has its own entry and root component.

| Window | Root | Kind |
| --- | --- | --- |
| `main` (the desk) | `App.vue` | Transparent, frameless, covers the monitor's work area; draws the own pet and room members' pets. On-top and click-through settings apply here. Never takes focus on Windows. |
| `panel` | `PanelApp.vue` | Regular resizable taskbar window. Created on first open, hidden on close; the desk keeps running. The tray and the pet's menu open it even while the desk is click-through. |
| `todo` | `TodoApp.vue` | Small frameless focusable window for the todo list. See [Todos](#todos). |
| `capture` | `CaptureApp.vue` (`capture.html`) | Off by default. See [Capture window](#capture-window). |

The hide key hides every window together and restores the ones that were open.

### Desk and panel

- The desk owns all network state: the room socket, activity reports and the presence heartbeat. Panel actions are requests the desk runs.
- `desktop/bridge.ts` mirrors player, collection, counter and room state to the panel with targeted Tauri events. The panel subscribes to separate slices while visible; only the room page subscribes to member runtime updates (coalesced per member every 50ms).
- Hiding or minimizing the panel drops its subscriptions and preview input but keeps a reveal in progress; reopening refreshes every slice. KeepAlive pages pause videos and auto scrolling when deactivated.
- Settings travel as property patches in both directions (`desktop/settingsSync.ts`). The desk relays the panel's patches to the todo window and back.
- Browser previews render the panel inside the desk page.

### Click-through

1. Interactive desk elements carry `data-hit`. `hit.ts` watches their size, position, insertion and removal and sends the boxes with `set_hit_regions`. Geometry animations are sampled only while they play.
2. A Rust thread (`spawn_hit_test`) checks the cursor against the regions and toggles `set_ignore_cursor_events`. It polls every 30ms while the cursor moves, every 100ms after two still seconds, and every 250ms while the pet is hidden or click-through.
3. While dragging (`set_dragging(true)`) the desk stays interactive until release.

### Todos

- Files: `todo.ts` (pure rules), `stores/todo.ts` (the list), `stores/todoClock.ts` (the desk's clock), `TodoApp.vue`, `todos/TodoRow.vue`, `todos/WhenPicker.vue`, `desktop/todoBridge.ts`.
- The list is kept on this device only, in the desk window's local storage (`asoultappo.todos`). The todo window and the panel read the desk's copy and change it through the bridge (`desktop:todos` to the window, `todo` and `todoSync` requests back).
- The window opens with `open_todo`, stays on top unless unpinned (`todoPinned`, `set_todo_on_top`), has no taskbar entry, and remembers its size (`todoW`, `todoH`) and place (`todoX`, `todoY`; first time at the bottom right of the pet's monitor).
- A todo has a title, an optional time (a day and a time of day, or a whole day that rings at 9:00) and a repeat (none, daily, working days, weekly).
- The desk steps the list every 5 seconds. A time rings once (`rang` records it, so a clock set back does not ring again); one found more than 2 minutes late rings without the tune.
- Rings go over the own pet through `stores/nudge.ts` (`offerTodo`): one todo gets its own bubble, several share one. Rings still waiting are stored (`asoultappo.todos.waiting`) and go up after the next start without the tune or notice again.
- Ticking off a repeating todo moves it to its next time. Ticked-off todos go after 7 days.
- The browser preview floats the same page (`?window=todo`) in a frame over the desk page (`pet/TodoFrame.vue`); the two pages follow each other through the storage event.

### Capture window

- A regular window (title bar, taskbar entry, not on top) that draws the own pet on a flat colour for recording software. OBS's window capture skips tool windows, and the desk is one (`tool_window.rs`). Follows WuwaTappoNative's capture window.
- `settings.captureOpen` is the only state. The desk opens or closes the window after it (`desktop/capture.ts`, `set_capture_window`); a window left open reopens at the next start at its last size (`captureW`, `captureH`).
- The page loads the pet's drawing only, no player or room code. It hears `input` events itself (`pet/PetPose.ts`); the desk sends it the rest (`capture:view`) at most once a frame.
- On macOS its web view keeps painting while covered (`paint_when_covered`). Not checked on Windows.

## Client: Rust (`client/src-tauri/src/`)

| File | Job |
| --- | --- |
| `lib.rs` | Desk commands, window lifecycle (panel, todo, capture), work-area sizing, tray menu |
| `input.rs` | Global keyboard and mouse hook (own low-level hooks on Windows, `rdev` on macOS). Emits `key_down`, `key_up`, `mouse_down/up{button}`, `mouse_move{dx,dy}`; never which key |
| `gamepad.rs`, `gamepad/playstation.rs` | Controller buttons from XInput (Windows) and Sony HID (DualShock 4, DualSense, Edge; USB and Bluetooth). The HID scan lists Sony devices only, every 5 seconds |
| `hit.rs`, `tool_window.rs` | Hit-region matching; keeps the desk out of other apps' occlusion checks on Windows |
| `overlay_macos.rs` | AppKit screen enumeration and work-area placement, on the main thread |
| `hotkey.rs` | Hide key and click-through key as system shortcuts |
| `access.rs` | macOS input permission check, reported without prompting |
| `elevation.rs` | Run as administrator and single instance on Windows |
| `autostart.rs` | Start at login: `SMAppService` (macOS 13+), LaunchAgent (10.15–12), HKCU `Run` (Windows) |
| `monitor_pref.rs` | The monitor picked from the tray |
| `update.rs` | Installs one exact version from its GitHub release |
| `applog.rs`, `diag.rs` | The log players export from settings; never window titles or keys |
| `media.rs` | Bundled pages and assets for the macOS web view, with byte ranges |

## Client: front end (`client/src/`)

| Path | Job |
| --- | --- |
| `App.vue`, `PanelApp.vue`, `TodoApp.vue`, `CaptureApp.vue` | Window roots |
| `desktop/` | State mirroring, settings patches, requests from the panel and the todo window to the desk |
| `pet/` | The pet and everything over it on the desk (see below) |
| `panel/` | The panel's pages and dialogs (see below) |
| `panel/park/` | 乐园: coins, scratch cards, race, lottery. Rules in `protocol/PROTOCOL.md` |
| `holo/` | WebGL shader for holo cards (镭射款) |
| `net/` | Room socket and HTTP API (see [Network](#network)) |
| `stores/` | Reactive state: `settings`, `player`, `room`, `desk`, `counter`, `pet`, `ui`, `theme`, `todo`, `nudge`, `pomodoro`, `activity` |
| `ui/` | Design tokens (`tokens.css`), shared components (`Icon`, `SegTabs`, `FilterChips`, `Modal`, `ItemArt`, `CharacterAvatar`, `RangeInput`) and helpers |
| `resonance.ts`, `reveal.ts`, `cards.ts`, `items.ts`, `scratch.ts`, `todo.ts`, … | Pure rules with their own tests |
| `test/` | Test helpers: example economy, pool sizes counted from the manifest |

Colours: the interface uses one coral, `#FC966E`, in `ui/tokens.css`. Member colours (嘉然 `#E799B0`, 乃琳 `#576690`, 贝拉 `#DB7D74`, 心宜 `#C93773`, 思诺 `#7252C0`) only mark members.

`Modal` and `RevealScene` teleport to `.panel-overlay` and carry `data-overlay`, so Esc closes them and not the panel.

### Desk (`pet/`)

- `PetView.vue` draws the layered pet; `PetActor.vue` drags it; `CounterBar.vue` is the strip with the tap count. The own actor keeps one width whatever the strip shows.
- `QuickEmote.vue` is the single-row emote dock. It starts with small keys for the tomato timer (`PomodoroDock.vue`), the todo window and, in a room, the own status (`StatusDock.vue`, `ui/StatusKeys.vue`).
- The strip folds to a grip; the pet can dock to the bottom edge. A click on the grip opens `GripMenu.vue`.
- Bubbles over the own pet: `EmoteBubble`, `ComboBubble`, `DuelBubble` (with `StakeKeys`), `PokeBubble`, `NudgeBubble` (reminders, tomato timer, todos), `CooldownBubble` (input faster than a hand), `AccessBubble` (macOS permission), `AdminBubble` (an elevated game the hook cannot hear). `duelPick.ts` opens poke, duel and profile keys over a partner's pet.
- Tomato timer: `pomodoro.ts`, `stores/pomodoro.ts`, `PomodoroChip.vue`. The system notice goes through `notify` in `lib.rs` (tauri-plugin-notification).

### Panel (`panel/`)

`MainPanel.vue` holds the sidebar, top bar and page shutter. Each page loads when first shown.

| Page | Content |
| --- | --- |
| `EmotesPage.vue` (背包) | Pet stage, eight favourite slots, wallet; shelves of skins and owned emotes. Only the shelves scroll |
| `ResonancePage.vue` (共鸣) | One pool for all members, a banner of dynamic cards, skin row, tier counts (`PoolStage.vue`), pity counters, draws, 衣橱 keys |
| `CollectionPage.vue` (图鉴) | Cards, emotes and skins; crafting in the detail; skin notes (`stores/skinNotes.ts`, this device only) |
| `CheckinPage.vue` (签到) | This month's calendar |
| `ParkPage.vue` (乐园) | The four park sections in `panel/park/` |
| `OnlinePage.vue` (联机) | Room table (`RoomStage.vue`), cheer bar, public room list, ticket, own status (`roomStatus.ts`), members |
| `CheerPage.vue` (排行) | Own namecard (`ProfileCard.vue`) and the collection board |
| `SettingsPage.vue` (设置) | Account, profile strip, then pet, window, online, sound and about groups in two columns |

Dialogs over the panel, one at a time in this order: `TermsDialog` (the desk stays offline until the current terms are agreed), `UpdateDialog` (cannot be closed below the server's minimum version), `NoticeBoard` (server announcements), `SkinSpotlight` (see [Adding skins](#adding-skins)), `UpdateRewardDialog`.

### Draw reveal

- `RevealScene.vue` lies over the page area. `RevealBands.vue` covers the page before `resonate` updates the stores; a third band in the best result's tone announces a hidden card or skin.
- `RevealTile.vue` deals one tile per draw. Rare and above land face down (`CardBack.vue`) and turn on a click; hidden cards, skins and a first dancing card lift into `RevealSpotlight.vue`.
- `reveal.ts` holds the pure rules; `reveal-board.ts` builds the tiles.
- Holo versions (`holo:<card id>`, `cards.ts`) are drawn by `holo/`: a shader over the art and its mask that follows a tilt toward the pointer (`HoloArt.vue`, `useTilt.ts`). A small pool of canvases means only the card under the pointer, the detail or the spotlight runs one. Without WebGL the art shows a still sheen.

### Cards and albums

- Card videos are bundled under `public/assets/cards/<series>/*.mp4` (`bundle:` URLs): H.264, 640 px wide, 30 fps, CRF 28, preset veryslow; audio up to 192 kbps copied, higher re-encoded to 192 kbps AAC. The server's packs hold the full-size still art.
- Albums: unowned cards stay in colour but dimmed and show still posters; up to three visible owned videos loop; offscreen videos release their source. The resonance stage plays every dynamic card at full brightness regardless of ownership.

## Network

- `net/`: `protocol.ts`, `TapBatcher.ts`, `MotionSender.ts`, `MotionFrames.ts`, `RoomClient.ts`, `api.ts`.
- `MotionSender` coalesces pet-layer offsets at 10Hz in quarter pixels, sends button edges at once and clears queued movement on disconnect.
- Packed motion (`motionVersion: 2` in `join` and `joined`, clients and servers after 1.1.3): a client sends `pose` with the changed fields and names the members it draws with `motion_subscribe`. The server answers with `motion_snapshot`, then `motion_delta` batches and `motion_edge` messages for subscribed members only. Older peers keep the full `motion` and `motion_batch` messages; both kinds share a room.
- `MotionFrames` keeps other members' poses outside Vue's reactive state. `PetView` writes the mouse and keyboard layers straight to their elements once a frame, and a 100ms CSS transition glides the mouse layer. A press shorter than a frame stays down for 70ms.
- A pet subscribes while its window is on screen and it is in view. The desk forwards poses to the panel's room page for the pets drawn there.

## Server (`server/app/`)

| File | Job |
| --- | --- |
| `main.py` | FastAPI app: `/ws` rooms, `/api/*` player endpoints, `/admin/*` for the main site's backend, `/packs` asset packs |
| `rooms.py` | Rooms in memory (up to 20 members): motion subscriptions and batches (100ms motion, 50ms button edges), per-connection writers, pokes, cheer progress. On stop it stores each room's listing, host and removed saves; for ten minutes after the next start it hands them back as members rejoin |
| `game.py` | Progression: income from taps, draws, check-in, scratch cards, duels, cheer rewards, update rewards, crafting, loadouts, the collection board. Every shard change goes to `shard_ledger` |
| `store.py` | SQLite access for everything above |
| `manifest.py` | Loads the catalog and builds the resonance pools, including the pool for an older client (`resonance_pool_for`) |
| `economy.py` | Loads the economy file named by `ASOULTAPPO_ECONOMY` |
| `cards.py`, `scratch.py` | Pure resonance and scratch rolls with an injectable RNG |
| `duel.py` | Rock-paper-scissors invites and timers in memory, bets in the store |
| `park.py`, `park_scratch.py`, `park_race.py`, `race.py`, `lottery.py`, `redeem.py` | 乐园: coins, scratch cards, race, lottery, redeem codes |
| `notice.py`, `releases.py` | Minimum client version and announcements; the newest release for the update check |
| `accounts.py`, `moderation.py` | Main-site account lookup; nickname blocklist pushed by the main site |
| `tracking.py`, `analytics.py` | Counts for the admin pages (client versions, room samples, daily counts) and their reports. Counts only: never what was said or shown, nor who did it to whom. Admin changes go to `admin_log` |

Pools: higher tiers prefer unowned items; a completed tier's odds move to common, except tiers the economy marks as repeating. Repeats turn into shards at once. Skins and cards with a `since` newer than the client stay out of its pool.

## Adding skins

A skin is one entry in `SKINS` (`scripts/asset_catalog.py`) plus `client/src/assets/characters/<member><series>/bgImage.webp`, fitted to the member's canvas so the paw layers line up. Then:

1. rebuild the previews (`scripts/build_previews.py`);
2. add a `HEADS` entry in `characters.ts` when the head top differs;
3. copy `SKINS` into both manifests;
4. rebuild the UI font subset for new names (`scripts/build_ui_assets.py`).

- `name` is the id (`<member><series>`, the save item and the room field) and never changes. `title` is the name on screen, the member followed by the skin's own name (`skinTitle` in `manifest.ts`).
- `since` is the release that ships the picture. The server keeps the skin out of older clients' pools, so the server can be deployed first.
- The skins sharing the newest `since` are that release's launch spotlight (`stores/spotlight.ts`, `panel/SkinSpotlight.vue`), shown once per device.
- Tests count skins and cards from the manifest, so they need no change.

## Performance notes

- Sticker grids mount the visible rows plus two rows of overscan. Dynamic emotes show static 160px covers in lists and play when previewed or sent.
- Pet backgrounds come in 480px and 960px variants, chosen by displayed scale; small avatars use a 264×224 crop (`scripts/build_previews.py`).
- `stores/activity.ts`: a window off screen stops pose subscriptions, name plate loops and mouse inertia. A desk with no input and no room event for 30 seconds pauses looping decoration only. The panel never idles.
- Each window loads its own chunk; each panel page loads when first shown, then the rest in the background.
- On macOS, asset decompression and byte-range copies run on blocking workers; the video cache keeps up to eight clips.
- Server: resonance keeps missing-item pools incrementally per transaction and writes history with one `executemany`. SQLite runs in WAL mode with `synchronous=NORMAL`; back up with `sqlite3 ... ".backup"`, since copying the `.db` alone misses the `-wal` file.
- Database timings and room traffic: `server/.venv/bin/python scripts/benchmark_server.py` (`--root` measures another checkout).
