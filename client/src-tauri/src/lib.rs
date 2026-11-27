#[macro_use]
mod applog;
mod access;
mod diag;
mod edition;
mod elevation;
mod gamepad;
mod hotkey;
mod hit;
mod input;
#[cfg(target_os = "macos")]
mod media;
mod autostart;
mod monitor_pref;
mod panel_place;
// Windows only at run time; its tap logic is plain code, tested everywhere.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
mod tablet;
#[cfg(target_os = "macos")]
mod overlay_macos;
#[cfg(target_os = "windows")]
mod tool_window;
#[cfg(target_os = "windows")]
mod transparency;
#[cfg(feature = "updater")]
mod update;

// Exactly one edition: the updater would let the standalone edition reach the network, and an online
// build without it could never update.
#[cfg(all(feature = "standalone", feature = "updater"))]
compile_error!("the standalone edition is built with `--no-default-features --features standalone`");
#[cfg(not(any(feature = "standalone", feature = "updater")))]
compile_error!("the online edition needs the default feature `updater`; the standalone one needs `--features standalone`");

use std::cell::Cell;
use std::path::PathBuf;
#[cfg(target_os = "windows")]
use std::sync::atomic::AtomicIsize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use hit::{HitRect, HitState};
#[cfg(target_os = "macos")]
use overlay_macos::{fit_to_monitor, monitor_count, monitor_keys, primary_index, window_rect};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};

/// How often the cursor is checked against the overlay's hit rectangles.
const HIT_TEST_INTERVAL: Duration = Duration::from_millis(30);
/// Poll interval while the overlay is hidden or click-through, when nothing can be hit.
const HIT_TEST_IDLE_INTERVAL: Duration = Duration::from_millis(250);
/// Poll interval once the cursor has stayed where it is for `HIT_TEST_STILL_AFTER`: what is under it changes
/// only when a pet's drawn parts do, and the first poll after it moves again brings the fast pace back.
const HIT_TEST_STILL_INTERVAL: Duration = Duration::from_millis(100);
const HIT_TEST_STILL_AFTER: Duration = Duration::from_secs(2);
/// Linux fallback: how long the hit test trusts the last `window.is_visible()` answer.
#[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
const HIT_VISIBLE_INTERVAL: Duration = Duration::from_millis(250);
/// How often the overlay checks that it still covers its monitor's work area
/// (monitor plugged/unplugged, resolution, scaling or taskbar changed).
const REFIT_INTERVAL: Duration = Duration::from_secs(2);
/// How often the hit test writes how many times the overlay took the mouse.
const HIT_SUMMARY_INTERVAL: Duration = Duration::from_secs(60);
/// Debug build: how often the hit test writes its full state while the pet can be hit.
const HIT_SNAPSHOT_INTERVAL: Duration = Duration::from_secs(5);
/// How often the Windows hit test checks the overlay's actual extended style against what it last set.
const STYLE_CHECK_INTERVAL: Duration = Duration::from_secs(1);
/// How long the pet window's real style may differ from what the hit test set before that is
/// logged (the style is applied on the main thread, a little after the hit test asks).
const STYLE_MISMATCH_GRACE: Duration = Duration::from_secs(1);

#[derive(Default)]
struct Overlay {
    hit: Mutex<HitState>,
    /// Index into the platform's monitor list (NSScreen::screens on macOS).
    monitor: Mutex<usize>,
    /// The overlay currently lets clicks through, so a mouse press lands on another window.
    passing: AtomicBool,
    /// The overlay moved or resized (tray, hotkey, or window event): its cached geometry is stale.
    moved: AtomicBool,
    /// Cached visibility of the overlay window (updated on show/hide and synced off the hot path).
    visible: AtomicBool,
    /// Windows: main overlay HWND for thread-safe `IsWindowVisible` without waking the UI thread.
    #[cfg(target_os = "windows")]
    hwnd: AtomicIsize,
}

/// Whether the frontend has called `set_popup_open` at least once (preserves legacy behavior before first call).
static POPUP_TRACKED: AtomicBool = AtomicBool::new(false);
/// Whether any desk popup currently needs `outside-click` events.
static POPUP_OPEN: AtomicBool = AtomicBool::new(false);
/// Whether the main desk window currently consumes `mouse_move` events (default true for compatibility).
static MAIN_MOUSE_ACTIVE: AtomicBool = AtomicBool::new(true);
static PANEL_MOUSE_ACTIVE: AtomicBool = AtomicBool::new(true);
static BOSS_HIDDEN: AtomicBool = AtomicBool::new(false);
/// Whether the panel window is currently shown.
static PANEL_VISIBLE: AtomicBool = AtomicBool::new(false);
/// Whether the capture window is currently open.
static CAPTURE_OPEN: AtomicBool = AtomicBool::new(false);
/// Whether the dou dizhu table window is currently open.
static DDZ_OPEN: AtomicBool = AtomicBool::new(false);

/// Minimum spacing for low-rate mouse activity pulses sent to `main` when 60 Hz mouse follow is off.
const MOUSE_PULSE_INTERVAL: Duration = Duration::from_secs(1);

fn outside_click_allowed(tracked: bool, open: bool) -> bool {
    !tracked || open
}

fn mouse_move_allowed(
    boss_hidden: bool,
    main_active: bool,
    panel_visible: bool,
    panel_active: bool,
    capture_open: bool,
    ddz_open: bool,
) -> bool {
    !boss_hidden && (main_active || (panel_visible && panel_active) || capture_open || ddz_open)
}

fn allow_mouse_pulse(last: &mut Option<Instant>, now: Instant) -> bool {
    if last.is_none_or(|prev| now.duration_since(prev) >= MOUSE_PULSE_INTERVAL) {
        *last = Some(now);
        true
    } else {
        false
    }
}

fn should_emit_outside_click() -> bool {
    outside_click_allowed(POPUP_TRACKED.load(Ordering::Acquire), POPUP_OPEN.load(Ordering::Relaxed))
}

fn should_emit_mouse_move() -> bool {
    mouse_move_allowed(
        BOSS_HIDDEN.load(Ordering::Relaxed),
        MAIN_MOUSE_ACTIVE.load(Ordering::Relaxed),
        PANEL_VISIBLE.load(Ordering::Relaxed),
        PANEL_MOUSE_ACTIVE.load(Ordering::Relaxed),
        CAPTURE_OPEN.load(Ordering::Relaxed),
        DDZ_OPEN.load(Ordering::Relaxed),
    )
}

fn main_window(app: &tauri::AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

/// Moves the pet to the next monitor and remembers it for the next start, from the tray or the hotkey (logged under
/// `from`). With [only_if_several] a single monitor is left alone; the tray still fits the overlay to it again.
fn move_to_next_monitor(app: &tauri::AppHandle, overlay: &Overlay, from: &str, only_if_several: bool) {
    let Some(w) = main_window(app) else { return };
    let count = monitor_count(&w).unwrap_or(1).max(1);
    if only_if_several && count < 2 {
        applog!(from, "next monitor: only one monitor");
        return;
    }
    if let Ok(mut m) = overlay.monitor.lock() {
        *m = (*m + 1) % count;
        fit_and_log(&w, *m, &format!("{from} next monitor, {count} monitor(s)"));
        overlay.moved.store(true, Ordering::Relaxed);
        let key = monitor_keys(&w).ok().and_then(|keys| keys.get(*m).cloned());
        if let Some(Err(e)) = key.map(|k| monitor_pref::save(app, &k)) {
            applog!(from, "remember monitor failed: {e}");
        }
    }
}

/// macOS gives a full-screen app a Space of its own. Without these flags the pet stays on the Space it
/// started on and is gone while another desktop or a full-screen app is shown. AppKit takes the change on the main
/// thread only and stops the app when it comes from another one (macOS 27: "Must only be used from the main
/// thread"). The todos' window is made in an async command, off the main thread, so the change goes through
/// `with_window`.
#[cfg(target_os = "macos")]
fn join_all_spaces(w: &WebviewWindow, tag: &str) {
    use objc2_app_kit::NSWindowCollectionBehavior as B;
    let joined = overlay_macos::with_window(w, |ns, _| {
        ns.setCollectionBehavior(ns.collectionBehavior() | B::CanJoinAllSpaces | B::FullScreenAuxiliary)
    });
    match joined {
        Ok(()) => applog!(tag, "joins all Spaces and full-screen apps"),
        Err(e) => applog!(tag, "join all Spaces failed: {e}"),
    }
}

/// Click-through: the overlay never takes the mouse (turn it off from the tray menu).
#[tauri::command]
fn set_click_through(overlay: tauri::State<'_, Arc<Overlay>>, enabled: bool) {
    if let Ok(mut st) = overlay.hit.lock() {
        if st.click_through != enabled {
            applog!("overlay", "click-through {}", on_off(enabled));
        }
        st.click_through = enabled;
    }
}

#[tauri::command]
fn set_always_on_top(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    if let Some(window) = main_window(&app) {
        if let Err(e) = window.set_always_on_top(enabled) {
            applog!("overlay", "always on top {} failed: {e}", on_off(enabled));
            return Err(e.to_string());
        }
        applog!("overlay", "always on top {}", on_off(enabled));
    }
    Ok(())
}

fn on_off(on: bool) -> &'static str {
    if on {
        "on"
    } else {
        "off"
    }
}

/// Where `export_log` wrote the file, and whether that is the desktop (else the downloads folder).
#[derive(serde::Serialize)]
struct ExportedLog {
    path: String,
    desktop: bool,
}

/// Copies the log to the desktop (or downloads) and shows it in the file manager.
#[tauri::command]
async fn export_log(app: tauri::AppHandle, overlay: tauri::State<'_, Arc<Overlay>>) -> Result<ExportedLog, String> {
    let overlay = overlay.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        log_state(&overlay, "export from the panel");
        export_log_files(&app)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// How much of the log goes with a feedback: within what the server takes (server/app/feedback.py LOG_MAX).
const FEEDBACK_LOG_BYTES: usize = 120 * 1024;

/// The latest part of the log, for a feedback the player sends with it from the settings page.
#[tauri::command]
async fn log_tail(overlay: tauri::State<'_, Arc<Overlay>>) -> Result<String, String> {
    let overlay = overlay.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        log_state(&overlay, "feedback sent with the log");
        applog::tail(FEEDBACK_LOG_BYTES)
    })
    .await
    .map_err(|e| e.to_string())
}

/// Whether this is the debug build (`--features debug-log`), which logs more from the page too.
#[tauri::command]
fn debug_log() -> bool {
    applog::DEBUG
}

/// Whether this runs elevated, whether the account could, and the player's choice.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct AdminStatus {
    supported: bool,
    elevated: bool,
    can_elevate: bool,
    run_as_admin: bool,
}

#[tauri::command]
fn admin_status() -> AdminStatus {
    AdminStatus {
        supported: cfg!(target_os = "windows"),
        elevated: elevation::is_elevated(),
        can_elevate: elevation::can_elevate(),
        run_as_admin: elevation::run_as_admin(),
    }
}

/// Turn "start as administrator" on or off. Turning it on while not elevated restarts through
/// UAC and answers "restarting" (this instance then exits); declining UAC answers "cancelled".
/// Runs on the main thread: ShellExecuteEx wants COM, and the pet may as well wait for UAC.
#[tauri::command]
fn set_run_as_admin(app: tauri::AppHandle, enabled: bool) -> Result<&'static str, String> {
    if !cfg!(target_os = "windows") {
        return Err("unsupported".into());
    }
    if !enabled || elevation::is_elevated() {
        elevation::set_run_as_admin(enabled).map_err(|e| e.to_string())?;
        applog!("app", "start as administrator {}", on_off(enabled));
        return Ok(if enabled { "on" } else { "off" });
    }
    if !elevation::can_elevate() {
        return Err("unavailable".into());
    }
    elevation::set_run_as_admin(true).map_err(|e| e.to_string())?;
    match elevation::restart_elevated() {
        Ok(()) => {
            applog!("app", "start as administrator on; restarting through UAC");
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_millis(300));
                app.exit(0);
            });
            Ok("restarting")
        }
        Err(e) => {
            let _ = elevation::set_run_as_admin(false);
            applog!("app", "restart as administrator failed: {e}");
            Err(e)
        }
    }
}

/// One line with the pet window's mouse state, the cursor and the foreground window, so an
/// exported log shows the moment it was exported.
fn log_state(overlay: &Overlay, why: &str) {
    let hit = overlay
        .hit
        .lock()
        .map(|st| {
            format!(
                "click-through {}, dragging {}, {} hit rects, page scale {}",
                on_off(st.click_through),
                st.dragging,
                st.rects.len(),
                st.page_scale.map_or_else(|| "not reported".to_string(), |s| s.to_string())
            )
        })
        .unwrap_or_else(|_| "hit state unavailable".into());
    let style = match diag::overlay_passes() {
        Some(true) => "passes the mouse",
        Some(false) => "takes the mouse",
        None => "unknown",
    };
    let set = if overlay.passing.load(Ordering::Relaxed) { "pass" } else { "take" };
    applog!(
        "app",
        "{why}: {hit}; hit test set the pet window to {set} the mouse, its style {style}; {}; {}",
        diag::under_cursor(),
        diag::foreground_detail()
    );
}

fn export_log_files(app: &tauri::AppHandle) -> Result<ExportedLog, String> {
    let paths = app.path();
    let targets: Vec<(PathBuf, bool)> = [(paths.desktop_dir(), true), (paths.download_dir(), false)]
        .into_iter()
        .filter_map(|(dir, desktop)| dir.ok().map(|d| (d, desktop)))
        .collect();
    let mut last_error = String::from("no desktop or downloads folder");
    for (dir, desktop) in targets {
        match applog::export(&dir) {
            Ok(path) => {
                applog!("app", "log exported");
                reveal(&path);
                return Ok(ExportedLog { path: path.display().to_string(), desktop });
            }
            Err(e) => last_error = e.to_string(),
        }
    }
    applog!("app", "log export failed: {last_error}");
    Err(last_error)
}

/// Opens the file manager with `path` selected.
fn reveal(path: &std::path::Path) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let _ = std::process::Command::new("explorer")
            .raw_arg(format!("/select,\"{}\"", path.display()))
            .spawn();
    }
    #[cfg(target_os = "macos")]
    let _ = std::process::Command::new("open").arg("-R").arg(path).spawn();
    #[cfg(all(unix, not(target_os = "macos")))]
    let _ = path;
}

/// A line from the page (errors, room connection), tagged `web:<tag>`.
#[tauri::command]
fn write_log(tag: String, msg: String) {
    let tag: String = tag
        .to_ascii_lowercase()
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
        .take(16)
        .collect();
    let msg: String = msg.chars().take(500).map(|c| if c == '\r' || c == '\n' { ' ' } else { c }).collect();
    applog::write(&format!("web:{tag}"), &msg);
}

/// A notice from the system for the tomato timer (src/stores/pomodoro.ts): it shows also while the pet is hidden or a
/// game fills the screen. In development builds it comes from the terminal or PowerShell instead of the app.
#[tauri::command]
fn notify(app: tauri::AppHandle, title: String, body: String) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;
    app.notification().builder().title(title).body(body).show().map_err(|e| {
        applog!("notify", "failed: {e}");
        e.to_string()
    })
}

/// The panel window was created and has not been shown yet: its first show places it (`place_panel`).
static PANEL_UNPLACED: AtomicBool = AtomicBool::new(false);

/// The size the player picked for the panel (`panelScale`, src/stores/settings.ts), sent by the desk.
static PANEL_SCALE: Mutex<f64> = Mutex::new(1.0);
/// The panel page's zoom now (`panel_place::fit`), put back when the window is shown or changes monitor.
static PANEL_ZOOM: Mutex<f64> = Mutex::new(1.0);

/// The panel on a monitor: its window's width and height in that monitor's pixels, and its page's zoom
/// (src/panel_place.rs, `fit`).
fn panel_size(area: &tauri::PhysicalRect<i32, u32>, scale: f64) -> (f64, f64, f64) {
    panel_place::fit(area.size.width as f64, area.size.height as f64, scale, panel_pick())
}

/// The size the panel is drawn at: the player's pick, or the page's own size where the web view cannot zoom.
fn panel_pick() -> f64 {
    panel_place::usable_pick(PANEL_SCALE.lock().map(|s| *s).unwrap_or(1.0), page_zoom_supported())
}

/// Whether the web view can zoom its page. wry sends `-[WKWebView setPageZoom:]`, which macOS has from 11 on; on an
/// older WebKit the message raises an Objective-C exception that ends the app. Asked once WebKit is loaded.
#[cfg(target_os = "macos")]
fn page_zoom_supported() -> bool {
    use objc2::{runtime::AnyClass, sel};
    static KNOWN: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    if let Some(known) = KNOWN.get() {
        return *known;
    }
    // Not loaded yet: no web view exists to zoom, and the answer is asked again next time.
    let Some(class) = AnyClass::get(c"WKWebView") else { return false };
    *KNOWN.get_or_init(|| {
        let known = class.responds_to(sel!(setPageZoom:));
        if !known {
            applog!("panel", "this WebKit has no page zoom: the panel stays at its own size");
        }
        known
    })
}

#[cfg(not(target_os = "macos"))]
fn page_zoom_supported() -> bool {
    true
}

/// Draws the panel's page at `zoom`: laid out at `panel_place::PAGE` in a window that size times `zoom`.
fn zoom_panel(panel: &WebviewWindow, zoom: f64) {
    if let Ok(mut now) = PANEL_ZOOM.lock() {
        *now = zoom;
    }
    // The page stays at its own size there (`panel_pick`), so there is nothing to set.
    if !page_zoom_supported() {
        return;
    }
    if let Err(e) = panel.set_zoom(zoom) {
        applog!("panel", "zoom {zoom:.2} failed: {e}");
    }
}

/// Puts the panel at `x`,`y` with a size of `w`×`h`, all in the pixels of the monitor whose scale is `scale`.
fn move_panel(panel: &WebviewWindow, x: f64, y: f64, w: f64, h: f64, scale: f64) -> tauri::Result<()> {
    // Tao turns a physical position into points with the window's own scale, which is the scale of the monitor it is
    // on now, not of the one it goes to.
    #[cfg(target_os = "macos")]
    let result = panel
        .set_size(tauri::LogicalSize::new(w / scale, h / scale))
        .and_then(|_| panel.set_position(tauri::LogicalPosition::new(x / scale, y / scale)));
    // Moved first: crossing to a monitor of another scale resizes the window, so the size is set once it is there.
    #[cfg(not(target_os = "macos"))]
    let result = {
        let _ = scale;
        let at = PhysicalPosition::new(x.round() as i32, y.round() as i32);
        panel
            .set_position(at)
            .and_then(|_| panel.set_size(PhysicalSize::new(w.round() as u32, h.round() as u32)))
            .and_then(|_| panel.set_position(at))
    };
    result
}

/// The size the player picked for the panel, from the desk at startup and on every change: a panel already placed
/// takes it at once, about its own centre and inside the work area of the monitor it is on.
#[tauri::command]
fn set_panel_scale(app: tauri::AppHandle, scale: f64) {
    if let Ok(mut picked) = PANEL_SCALE.lock() {
        *picked = scale;
    }
    let Some(panel) = app.get_webview_window("panel") else { return };
    // Not shown yet: its first show sizes it (`place_panel`).
    if PANEL_UNPLACED.load(Ordering::Relaxed) {
        return;
    }
    refit_panel(&panel, &format!("scaled to {scale:.2}"));
}

/// The work area and scale the panel was last fitted to (`panel_place::Home`).
static PANEL_HOME: Mutex<Option<panel_place::Home>> = Mutex::new(None);

fn panel_home(area: &tauri::PhysicalRect<i32, u32>, scale: f64) -> panel_place::Home {
    panel_place::Home {
        area: panel_place::Rect {
            x: area.position.x as f64,
            y: area.position.y as f64,
            w: area.size.width as f64,
            h: area.size.height as f64,
        },
        scale,
    }
}

fn set_panel_home(home: panel_place::Home) {
    if let Ok(mut now) = PANEL_HOME.lock() {
        *now = Some(home);
    }
}

/// Sizes the panel for the monitor it is on now at the size the player picked, about its own centre and inside that
/// monitor's work area (`panel_place::refit`). `why` starts the log line.
fn refit_panel(panel: &WebviewWindow, why: &str) {
    let monitor = match panel.current_monitor() {
        Ok(Some(m)) => m,
        _ => return applog!("panel", "{why}: its monitor is unknown"),
    };
    let monitor_scale = monitor.scale_factor();
    let home = panel_home(monitor.work_area(), monitor_scale);
    let (Ok(at), Ok(size)) = (panel.outer_position(), panel.outer_size()) else { return };
    // The window's own pixels are the monitor's: it is on that monitor.
    let at = panel_place::Rect { x: at.x as f64, y: at.y as f64, w: size.width as f64, h: size.height as f64 };
    let (to, zoom) = panel_place::refit(home.area, monitor_scale, panel_pick(), at);
    // Before the window moves: the move it makes is not one to answer (`panel_moved`).
    set_panel_home(home);
    // Between the two steps the page is laid out larger than its own size, never smaller: its container queries all
    // look for less room, so nothing in it changes shape on the way.
    let growing = zoom > PANEL_ZOOM.lock().map(|z| *z).unwrap_or(1.0);
    if !growing {
        zoom_panel(panel, zoom);
    }
    let moved = move_panel(panel, to.x, to.y, to.w, to.h, monitor_scale);
    if growing {
        zoom_panel(panel, zoom);
    }
    match moved {
        Ok(()) => applog!("panel", "{why}: zoom {zoom:.2}, {:.0}x{:.0}", to.w, to.h),
        Err(e) => applog!("panel", "{why}: failed: {e}"),
    }
}

/// How long the panel has to stay where it is before a move counts as finished.
const PANEL_SETTLE: Duration = Duration::from_millis(400);
/// When the panel last moved.
static PANEL_MOVED_AT: Mutex<Option<Instant>> = Mutex::new(None);
/// A thread is waiting for the panel's move to finish (`panel_moved`).
static PANEL_SETTLING: AtomicBool = AtomicBool::new(false);

/// Whether the player may still be dragging a window: the primary mouse button is down. Elsewhere a pause is the
/// only sign.
fn window_drag_held() -> bool {
    #[cfg(target_os = "windows")]
    return primary_button_down();
    #[cfg(target_os = "macos")]
    {
        use objc2::{msg_send, runtime::AnyClass};
        // SAFETY: `+[NSEvent pressedMouseButtons]` reads the buttons' state and may be asked from any thread.
        return AnyClass::get(c"NSEvent").is_some_and(|class| {
            let buttons: usize = unsafe { msg_send![class, pressedMouseButtons] };
            buttons & 1 != 0
        });
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    false
}

/// The panel moved. Once it stays put, a panel that reached another monitor, or whose monitor's work area or scale
/// changed, is fitted to it again at the size the player picked (it cannot be resized by hand). The window reports
/// many moves while it is dragged; one thread waits for the last of them.
fn panel_moved(app: &tauri::AppHandle) {
    if let Ok(mut at) = PANEL_MOVED_AT.lock() {
        *at = Some(Instant::now());
    }
    if PANEL_SETTLING.swap(true, Ordering::AcqRel) {
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(Duration::from_millis(100));
            let quiet = PANEL_MOVED_AT.lock().ok().and_then(|at| *at).is_none_or(|at| at.elapsed() >= PANEL_SETTLE);
            if quiet && !window_drag_held() {
                break;
            }
        }
        PANEL_SETTLING.store(false, Ordering::Release);
        let Some(panel) = app.get_webview_window("panel") else { return };
        // A minimized window is moved off every monitor (Windows); a hidden or unplaced one is fitted when shown.
        if PANEL_UNPLACED.load(Ordering::Relaxed)
            || !panel.is_visible().unwrap_or(false)
            || panel.is_minimized().unwrap_or(true)
        {
            return;
        }
        let Ok(Some(monitor)) = panel.current_monitor() else { return };
        let now = panel_home(monitor.work_area(), monitor.scale_factor());
        let home = PANEL_HOME.lock().ok().and_then(|h| *h);
        if panel_place::left_home(home, now) {
            refit_panel(&panel, "moved to another monitor or work area");
        }
    });
}

/// Where the overlay's page starts, in its monitor's pixels (`Monitor::work_area`'s units).
#[cfg(not(target_os = "macos"))]
fn overlay_origin(overlay: &WebviewWindow, _area: &tauri::PhysicalRect<i32, u32>) -> Option<(f64, f64)> {
    overlay.inner_position().ok().map(|p| (p.x as f64, p.y as f64))
}

/// macOS: the overlay covers its screen's visible frame, which is the monitor's work area.
#[cfg(target_os = "macos")]
fn overlay_origin(_overlay: &WebviewWindow, area: &tauri::PhysicalRect<i32, u32>) -> Option<(f64, f64)> {
    Some((area.position.x as f64, area.position.y as f64))
}

/// Centre the panel on the pet's monitor, or move it just clear of what the desk draws there (src/panel_place.rs).
/// Done at its first show, not at creation: at the very first start the desk opens the panel before it has reported
/// what it draws.
fn place_panel(app: &tauri::AppHandle, panel: &WebviewWindow) {
    let Some(overlay) = main_window(app) else { return };
    let monitor = match overlay.current_monitor() {
        Ok(Some(m)) => m,
        Ok(None) => return applog!("panel", "place: the pet's monitor is unknown"),
        Err(e) => return applog!("panel", "place: the pet's monitor is unknown: {e}"),
    };
    let area = *monitor.work_area();
    let scale = monitor.scale_factor();
    let (w, h, zoom) = panel_size(&area, scale);
    // CSS px times the page's device pixel ratio are the monitor's pixels: physical pixels on Windows, points times
    // the backing scale on macOS (how tauri reports a monitor there).
    let avoid: Vec<panel_place::Rect> = match (overlay.is_visible(), overlay_origin(&overlay, &area)) {
        (Ok(true), Some((ox, oy))) => {
            let (rects, page_scale) = app
                .state::<Arc<Overlay>>()
                .hit
                .lock()
                .map(|st| (st.rects.clone(), st.page_scale))
                .unwrap_or_default();
            let k = page_scale.unwrap_or(scale);
            rects
                .iter()
                .map(|r| panel_place::Rect { x: ox + r.x * k, y: oy + r.y * k, w: r.w * k, h: r.h * k })
                .collect()
        }
        _ => Vec::new(),
    };
    let bounds = panel_place::Rect {
        x: area.position.x as f64,
        y: area.position.y as f64,
        w: area.size.width as f64,
        h: area.size.height as f64,
    };
    let (x, y) = panel_place::place(bounds, w, h, &avoid, 16.0 * scale, 10.0 * scale);
    let covered = panel_place::covered(&panel_place::Rect { x, y, w, h }, &avoid);
    set_panel_home(panel_home(&area, scale));
    zoom_panel(panel, zoom);
    match move_panel(panel, x, y, w, h, scale) {
        Ok(()) => applog!(
            "panel",
            "placed at {:.0},{:.0} ({:.0}x{:.0}, zoom {:.2}) on the pet's monitor, {} area(s) to avoid, {:.0} px² of them covered",
            x,
            y,
            w,
            h,
            zoom,
            avoid.len(),
            covered
        ),
        Err(e) => applog!("panel", "place failed: {e}"),
    }
}

#[tauri::command]
fn show_panel(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("panel") {
        if PANEL_UNPLACED.swap(false, Ordering::Relaxed) {
            place_panel(&app, &window);
        } else {
            // Kept by the webview as far as known; set again in case a platform drops it.
            zoom_panel(&window, PANEL_ZOOM.lock().map(|z| *z).unwrap_or(1.0));
        }
        window.unminimize().map_err(|e| e.to_string())?;
        window.show().map_err(|e| e.to_string())?;
        PANEL_VISIBLE.store(true, Ordering::Relaxed);
        window.set_focus().map_err(|e| e.to_string())?;
        app.emit_to("panel", "panel:visible", true).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn panel_hidden() {
    if PANEL_VISIBLE.swap(false, Ordering::Relaxed) {
        #[cfg(target_os = "macos")]
        media::clear_video_cache();
    }
}

#[tauri::command]
fn hide_panel(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("panel") {
        window.hide().map_err(|e| e.to_string())?;
        panel_hidden();
        app.emit_to("panel", "panel:visible", false).map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// A regular taskbar window. The first load asks the desk for its current state
/// before showing; later opens reuse the panel and its selected page.
#[tauri::command]
async fn open_panel(
    app: tauri::AppHandle,
    page: Option<String>,
    craft_target: Option<String>,
) -> Result<(), String> {
    if app.get_webview_window("panel").is_some() {
        app.emit_to("panel", "panel:open", serde_json::json!({ "page": page, "craftTarget": craft_target }))
            .map_err(|e| e.to_string())?;
        return show_panel(app);
    }
    let window = WebviewWindowBuilder::new(&app, "panel", WebviewUrl::App("index.html?window=panel".into()))
        .title(edition::DISPLAY_NAME)
        .inner_size(panel_place::PAGE.0, panel_place::PAGE.1)
        .min_inner_size(640.0, 480.0)
        // Its size comes from the settings only (`set_panel_scale`): the page is laid out for one proportion.
        .resizable(false)
        .maximizable(false)
        .transparent(true)
        .decorations(false)
        .always_on_top(false)
        .skip_taskbar(false)
        .shadow(false)
        .visible(false)
        .focused(false)
        // macOS: a click on the window while another one is in front is a click on its page as well, not only a
        // switch to it (the pet window does the same, tauri.conf.json).
        .accept_first_mouse(true)
        .build()
        .map_err(|e| {
            applog!("panel", "create failed: {e}");
            e.to_string()
        })?;
    applog!("panel", "created");
    if let Some(monitor) = window.current_monitor().map_err(|e| e.to_string())? {
        let (w, h, zoom) = panel_size(monitor.work_area(), monitor.scale_factor());
        window.set_size(PhysicalSize::new(w as u32, h as u32)).map_err(|e| e.to_string())?;
        zoom_panel(&window, zoom);
    }
    window.center().map_err(|e| e.to_string())?;
    // Its first show moves it to the pet's monitor, clear of the pet.
    PANEL_UNPLACED.store(true, Ordering::Relaxed);
    Ok(())
}

/// The desk listens to the tray now: a second start of the program (Windows) can raise the panel from here on.
#[tauri::command]
fn watch_second_start(app: tauri::AppHandle) {
    elevation::spawn_show_listener(app);
}

#[tauri::command]
async fn toggle_panel(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("panel") {
        if window.is_visible().map_err(|e| e.to_string())? && !window.is_minimized().map_err(|e| e.to_string())? {
            return hide_panel(app);
        }
    }
    open_panel(app, None, None).await
}

/// The todos' window, in logical pixels: a card with its own title bar on a transparent window.
const TODO_SIZE: (f64, f64) = (320.0, 460.0);
/// The race's window, in logical pixels (the browser preview's frame is the same size: src/pet/RaceFrame.vue).
#[cfg(not(feature = "standalone"))]
const RACE_SIZE: (f64, f64) = (1180.0, 740.0);
/// The dou dizhu table's window, in logical pixels (the browser preview's frame is the same size: src/pet/DdzFrame.vue).
const DDZ_SIZE: (f64, f64) = (1180.0, 740.0);
/// The smallest it gets: the table's stage (src/panel/ddz/DdzTable.vue, BASE) at its own size.
const DDZ_MIN_SIZE: (f64, f64) = (960.0, 640.0);
/// Its distance from the corner of the work area the first time it opens, in logical pixels.
const TODO_MARGIN: f64 = 24.0;

fn show_window(window: &WebviewWindow) -> Result<(), String> {
    window.unminimize().map_err(|e| e.to_string())?;
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())
}

/// The todos' window: small, frameless, over other windows unless unpinned, not in the taskbar, and a regular
/// window that takes the keyboard (the overlay never does on Windows). Closing hides it, so it opens again at once.
/// `x`, `y`: where it was left, in screen pixels, used while that spot is on a monitor; otherwise it goes to the
/// bottom right of the pet's monitor. The page shows it once it has drawn (`show_todo`). Moves are reported to the
/// desk (`todo:moved`), which keeps the spot.
#[tauri::command]
async fn open_todo(
    app: tauri::AppHandle,
    x: Option<i32>,
    y: Option<i32>,
    w: Option<f64>,
    h: Option<f64>,
    on_top: bool,
) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("todo") {
        return show_window(&window);
    }
    let window = WebviewWindowBuilder::new(&app, "todo", WebviewUrl::App("index.html?window=todo".into()))
        .title("待办")
        .inner_size(w.unwrap_or(TODO_SIZE.0), h.unwrap_or(TODO_SIZE.1))
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(on_top)
        .skip_taskbar(true)
        .visible(false)
        .focused(false)
        .accept_first_mouse(true)
        .build()
        .map_err(|e| {
            applog!("todo", "create failed: {e}");
            e.to_string()
        })?;
    applog!("todo", "created");
    #[cfg(target_os = "macos")]
    join_all_spaces(&window, "todo");
    match x.zip(y).filter(|&(x, y)| on_a_monitor(&window, x, y)) {
        Some((x, y)) => window.set_position(PhysicalPosition::new(x, y)).map_err(|e| e.to_string())?,
        None => place_todo(&app, &window)?,
    }
    Ok(())
}

/// A spot just inside the top of a window placed at `x`, `y` lies in some monitor's work area: its title bar can
/// be reached to move it.
fn on_a_monitor(window: &WebviewWindow, x: i32, y: i32) -> bool {
    let (px, py) = (x + (TODO_SIZE.0 / 2.0) as i32, y + 16);
    window.available_monitors().is_ok_and(|monitors| {
        monitors.iter().any(|m| {
            let area = m.work_area();
            px >= area.position.x
                && py >= area.position.y
                && px < area.position.x + area.size.width as i32
                && py < area.position.y + area.size.height as i32
        })
    })
}

/// The first spot of the todos' window: the bottom right of the work area of the pet's monitor.
fn place_todo(app: &tauri::AppHandle, window: &WebviewWindow) -> Result<(), String> {
    let monitor = main_window(app)
        .and_then(|w| w.current_monitor().ok().flatten())
        .or_else(|| window.current_monitor().ok().flatten());
    let Some(monitor) = monitor else { return Ok(()) };
    let area = monitor.work_area();
    let scale = monitor.scale_factor();
    // Its own size: the page may have set another one with the grip at its corner.
    let size = window.outer_size().map_err(|e| e.to_string())?;
    let (w, h, margin) = (size.width as i32, size.height as i32, (TODO_MARGIN * scale) as i32);
    window
        .set_position(PhysicalPosition::new(
            area.position.x + area.size.width as i32 - w - margin,
            area.position.y + area.size.height as i32 - h - margin,
        ))
        .map_err(|e| e.to_string())
}

/// The race's own window: the page that watches a dumpling race, frameless, a regular window in the taskbar, as
/// large as `RACE_SIZE` or the work area allows, in the middle of its monitor. `replay` is the finished race it
/// plays, none for the live one: a window already open is told (`race:open`) and brought to the front. The page
/// shows it once it has drawn (`show_race`). Closing it closes it: the next call makes it again.
/// The race needs the server, so the standalone edition has no race window.
#[cfg(not(feature = "standalone"))]
#[tauri::command]
async fn open_race(app: tauri::AppHandle, replay: Option<i64>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("race") {
        app.emit_to("race", "race:open", replay).map_err(|e| e.to_string())?;
        return show_window(&window);
    }
    let url = match replay {
        Some(id) => format!("index.html?window=race&replay={id}"),
        None => "index.html?window=race".to_string(),
    };
    let window = WebviewWindowBuilder::new(&app, "race", WebviewUrl::App(url.into()))
        .title("团子赛跑")
        .inner_size(RACE_SIZE.0, RACE_SIZE.1)
        .min_inner_size(880.0, 560.0)
        .maximizable(false)
        .transparent(true)
        .decorations(false)
        .always_on_top(false)
        .skip_taskbar(false)
        .shadow(false)
        .visible(false)
        .focused(false)
        .accept_first_mouse(true)
        .build()
        .map_err(|e| {
            applog!("race", "create failed: {e}");
            e.to_string()
        })?;
    applog!("race", "created");
    if let Some(monitor) = window.current_monitor().map_err(|e| e.to_string())? {
        let area = monitor.work_area();
        let scale = monitor.scale_factor();
        window.set_size(PhysicalSize::new(
            (RACE_SIZE.0 * scale).min(area.size.width as f64 - 20.0) as u32,
            (RACE_SIZE.1 * scale).min(area.size.height as f64 - 20.0) as u32,
        )).map_err(|e| e.to_string())?;
    }
    window.center().map_err(|e| e.to_string())
}

#[cfg(not(feature = "standalone"))]
#[tauri::command]
fn show_race(app: tauri::AppHandle) -> Result<(), String> {
    match app.get_webview_window("race") {
        Some(window) => show_window(&window),
        None => Ok(()),
    }
}

#[cfg(not(feature = "standalone"))]
#[tauri::command]
fn close_race(app: tauri::AppHandle) -> Result<(), String> {
    match app.get_webview_window("race") {
        Some(window) => window.close().map_err(|e| e.to_string()),
        None => Ok(()),
    }
}

/// The dou dizhu table's own window: frameless, a regular window in the taskbar, as large as `DDZ_SIZE` or the work
/// area allows, in the middle of its monitor. The desk opens it with each deal; a window already open is brought to
/// the front. The page shows it once it has drawn (`show_ddz`). Closing it closes it (the desk hears `ddz:closed`)
/// and leaves the game going: the next call makes it again. `auto`: opened by a deal, not by the player; then it
/// stays shut while the hide key has the pet hidden, and the answer is false. Opened by a deal, it also asks for the
/// player's attention (the taskbar button flashes on Windows): at once when it was open already, else once the page
/// has drawn and shows it (`show_ddz`).
#[tauri::command]
async fn open_ddz(app: tauri::AppHandle, auto: Option<bool>) -> Result<bool, String> {
    let auto = auto.unwrap_or(false);
    if auto && !main_window(&app).is_some_and(|w| w.is_visible().unwrap_or(true)) {
        applog!("ddz", "not opened: the pet is hidden");
        return Ok(false);
    }
    if let Some(window) = app.get_webview_window("ddz") {
        show_window(&window)?;
        DDZ_OPEN.store(true, Ordering::Relaxed);
        if auto {
            attention(&window);
        }
        return Ok(true);
    }
    let window = WebviewWindowBuilder::new(&app, "ddz", WebviewUrl::App("index.html?window=ddz".into()))
        .title("斗地主")
        .inner_size(DDZ_SIZE.0, DDZ_SIZE.1)
        .min_inner_size(DDZ_MIN_SIZE.0, DDZ_MIN_SIZE.1)
        .maximizable(false)
        .transparent(true)
        .decorations(false)
        .always_on_top(false)
        .skip_taskbar(false)
        .shadow(false)
        .visible(false)
        .focused(false)
        .accept_first_mouse(true)
        .build()
        .map_err(|e| {
            applog!("ddz", "create failed: {e}");
            e.to_string()
        })?;
    applog!("ddz", "created");
    DDZ_OPEN.store(true, Ordering::Relaxed);
    DDZ_ATTENTION.store(auto, Ordering::Relaxed);
    if let Some(monitor) = window.current_monitor().map_err(|e| e.to_string())? {
        let area = monitor.work_area();
        let scale = monitor.scale_factor();
        window.set_size(PhysicalSize::new(
            (DDZ_SIZE.0 * scale).min(area.size.width as f64 - 20.0) as u32,
            (DDZ_SIZE.1 * scale).min(area.size.height as f64 - 20.0) as u32,
        )).map_err(|e| e.to_string())?;
    }
    window.center().map_err(|e| e.to_string())?;
    Ok(true)
}

/// The table's window being made was opened by a deal: `show_ddz` asks for attention once it shows it.
static DDZ_ATTENTION: AtomicBool = AtomicBool::new(false);

/// Asks for the player's attention to [window] without taking it from them (Informational: a short flash).
fn attention(window: &WebviewWindow) {
    if let Err(e) = window.request_user_attention(Some(tauri::UserAttentionType::Informational)) {
        applog!("ddz", "attention failed: {e}");
    }
}

#[tauri::command]
fn show_ddz(app: tauri::AppHandle) -> Result<(), String> {
    match app.get_webview_window("ddz") {
        Some(window) => {
            show_window(&window)?;
            DDZ_OPEN.store(true, Ordering::Relaxed);
            if DDZ_ATTENTION.swap(false, Ordering::Relaxed) {
                attention(&window);
            }
            Ok(())
        }
        None => Ok(()),
    }
}

#[tauri::command]
fn close_ddz(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("ddz") {
        window.close().map_err(|e| e.to_string())?;
    }
    DDZ_OPEN.store(false, Ordering::Relaxed);
    Ok(())
}

#[tauri::command]
fn show_todo(app: tauri::AppHandle) -> Result<(), String> {
    match app.get_webview_window("todo") {
        Some(window) => show_window(&window),
        None => Ok(()),
    }
}

#[tauri::command]
fn hide_todo(app: tauri::AppHandle) -> Result<(), String> {
    match app.get_webview_window("todo") {
        Some(window) => window.hide().map_err(|e| e.to_string()),
        None => Ok(()),
    }
}

/// The pin of the todos' window: over other windows or not.
#[tauri::command]
fn set_todo_on_top(app: tauri::AppHandle, on: bool) -> Result<(), String> {
    match app.get_webview_window("todo") {
        Some(window) => window.set_always_on_top(on).map_err(|e| e.to_string()),
        None => Ok(()),
    }
}

/// WebKit stops painting a web view once its window is fully covered. The capture window is usually behind
/// the game being recorded, and recording software reads covered windows as well, so its web view is told
/// not to check. `_setWindowOcclusionDetectionEnabled:` is WebKit's own switch for this, not public API:
/// without it the pet stands still while covered and nothing else changes.
#[cfg(target_os = "macos")]
fn paint_when_covered(window: &WebviewWindow) {
    use objc2::{msg_send, runtime::AnyObject, sel};
    let result = window.with_webview(|webview| {
        let view = webview.inner() as *mut AnyObject;
        // SAFETY: Tauri hands out the window's live WKWebView and runs this on the main thread; the
        // message is sent only when the view answers to it.
        let known = unsafe {
            match view.as_ref() {
                Some(view) if msg_send![view, respondsToSelector: sel!(_setWindowOcclusionDetectionEnabled:)] => {
                    let _: () = msg_send![view, _setWindowOcclusionDetectionEnabled: false];
                    true
                }
                _ => false,
            }
        };
        applog!("capture", "paints while covered: {}", if known { "on" } else { "not available in this WebKit" });
    });
    if let Err(e) = result {
        applog!("capture", "paints while covered: failed ({e})");
    }
}

/// Opens or closes the capture window: a regular window (title bar, taskbar entry, not a tool window, not
/// on top) with the own pet on a flat colour. OBS's window capture leaves tool windows out of its list
/// (`check_window_valid`, plugins/win-capture/window-capture.c), which is what the desk overlay is
/// (src/tool_window.rs). Its close button reports to the desk, which keeps the setting. The arrangement is
/// the one WuwaTappoNative uses for the same purpose (src/Pet/CaptureWindow.cs there).
#[tauri::command]
async fn set_capture_window(app: tauri::AppHandle, open: bool, width: f64, height: f64) -> Result<(), String> {
    let existing = app.get_webview_window("capture");
    if !open {
        if let Some(window) = existing {
            applog!("capture", "close");
            window.destroy().map_err(|e| e.to_string())?;
        }
        CAPTURE_OPEN.store(false, Ordering::Relaxed);
        return Ok(());
    }
    if let Some(window) = existing {
        window.unminimize().map_err(|e| e.to_string())?;
        window.show().map_err(|e| e.to_string())?;
        CAPTURE_OPEN.store(true, Ordering::Relaxed);
        return Ok(());
    }
    let (width, height) = (width.clamp(160.0, 1600.0), height.clamp(160.0, 1600.0));
    let window = WebviewWindowBuilder::new(&app, "capture", WebviewUrl::App("capture.html".into()))
        .title(format!("{} 采集窗口", edition::DISPLAY_NAME))
        // The size it was last dragged to (settings.captureW, captureH), reported from the window's own
        // resize events below: the same measure as this one, which the page's viewport is not on macOS
        // (shorter by the title bar).
        .inner_size(width, height)
        .min_inner_size(160.0, 160.0)
        .max_inner_size(1600.0, 1600.0)
        .always_on_top(false)
        .skip_taskbar(false)
        // Opened from the panel or the tray, or at startup: none of them should lose the keyboard to it.
        .focused(false)
        .build()
        .map_err(|e| {
            applog!("capture", "create failed: {e}");
            e.to_string()
        })?;
    applog!("capture", "created");
    CAPTURE_OPEN.store(true, Ordering::Relaxed);
    #[cfg(target_os = "macos")]
    paint_when_covered(&window);
    #[cfg(not(target_os = "macos"))]
    let _ = window;
    Ok(())
}

/// Opens one of the edition's About links (src/edition.rs) in the system browser or mail app.
#[tauri::command]
fn open_about_link(url: String) -> Result<(), String> {
    if !edition::ABOUT_LINKS.contains(&url.as_str()) {
        return Err("unknown link".into());
    }
    // Started from an elevated process the browser would run elevated too; explorer hands the
    // link to the shell, which runs with the player's normal rights. Explorer reads `=` and `,`
    // in its argument as option separators, so a link with a query string opened the Documents
    // folder; the link goes into an Internet Shortcut file and explorer opens that file instead.
    #[cfg(target_os = "windows")]
    let result = if elevation::is_elevated() {
        let shortcut = std::env::temp_dir().join("AsoulTappo-link.url");
        std::fs::write(&shortcut, format!("[InternetShortcut]\r\nURL={url}\r\n"))
            .and_then(|()| std::process::Command::new("explorer").arg(&shortcut).spawn())
    } else {
        std::process::Command::new("rundll32").args(["url.dll,FileProtocolHandler", &url]).spawn()
    };
    #[cfg(target_os = "macos")]
    let result = std::process::Command::new("open").arg(&url).spawn();
    #[cfg(all(unix, not(target_os = "macos")))]
    let result = std::process::Command::new("xdg-open").arg(&url).spawn();
    result.map(|_| ()).map_err(|e| e.to_string())
}

/// Areas (CSS px) where the overlay draws something and should take the mouse, and the
/// page's device pixel ratio that turns them into screen pixels.
#[tauri::command]
fn set_hit_regions(
    window: WebviewWindow,
    overlay: tauri::State<'_, Arc<Overlay>>,
    rects: Vec<HitRect>,
    scale: Option<f64>,
) {
    let scale = scale.filter(|s| s.is_finite() && *s > 0.0);
    let changed = match overlay.hit.lock() {
        Ok(mut st) => {
            st.rects = rects;
            std::mem::replace(&mut st.page_scale, scale) != scale
        }
        Err(_) => false,
    };
    if let (true, Some(page)) = (changed, scale) {
        match window.scale_factor() {
            Ok(monitor) => applog!("overlay", "page scale {page}, monitor scale {monitor}"),
            Err(e) => applog!("overlay", "page scale {page}, monitor scale unavailable: {e}"),
        }
    }
}

/// Keep taking the mouse while a pet is being dragged.
#[tauri::command]
fn set_dragging(overlay: tauri::State<'_, Arc<Overlay>>, active: bool) {
    if let Ok(mut st) = overlay.hit.lock() {
        st.dragging = active;
    }
}

/// Whether any desk popup currently needs `outside-click` events.
#[tauri::command]
fn set_popup_open(open: bool) {
    POPUP_OPEN.store(open, Ordering::Relaxed);
    POPUP_TRACKED.store(true, Ordering::Release);
}

/// Whether `label` currently consumes `mouse_move` events.
#[tauri::command]
fn set_mouse_active(label: String, active: bool) {
    match label.as_str() {
        "main" => MAIN_MOUSE_ACTIVE.store(active, Ordering::Relaxed),
        "panel" => PANEL_MOUSE_ACTIVE.store(active, Ordering::Relaxed),
        _ => {}
    }
}

/// Cover the work area (the monitor minus the taskbar) of monitor `index`;
/// an unknown index falls back to the primary monitor. Returns the area and the
/// monitor's scale factor, for the log.
#[cfg(not(target_os = "macos"))]
fn fit_to_monitor(window: &WebviewWindow, index: usize) -> tauri::Result<Option<String>> {
    let monitors = window.available_monitors()?;
    let primary = window.primary_monitor()?;
    let Some(m) = monitors.get(index).or(primary.as_ref()).or(monitors.first()) else {
        return Ok(None);
    };
    let (x, y, w, h) = overlay_area(m);
    window.set_position(PhysicalPosition::new(x, y))?;
    window.set_size(PhysicalSize::new(w, h))?;
    Ok(Some(format!("{} at scale {}", rect_text(x, y, w, h), m.scale_factor())))
}

/// The rectangle the overlay takes on a monitor: its work area.
///
/// On Windows an auto-hiding taskbar leaves the work area as large as the monitor. A topmost
/// window covering the whole monitor counts as a full-screen app there, and the hidden taskbar
/// stops coming up at the screen edge, so the overlay then keeps one pixel clear on every side.
#[cfg(not(target_os = "macos"))]
fn overlay_area(m: &tauri::Monitor) -> (i32, i32, u32, u32) {
    let area = m.work_area();
    let (x, y, w, h) = (area.position.x, area.position.y, area.size.width, area.size.height);
    #[cfg(windows)]
    if area.position == *m.position() && area.size == *m.size() && w > 2 && h > 2 {
        return (x + 1, y + 1, w - 2, h - 2);
    }
    (x, y, w, h)
}

/// Fit to monitor `index` and log the result under `why`.
fn fit_and_log(window: &WebviewWindow, index: usize, why: &str) {
    match fit_to_monitor(window, index) {
        Ok(Some(area)) => applog!("overlay", "{why}: monitor {index}, work area {area}"),
        Ok(None) => applog!("overlay", "{why}: no monitor found"),
        Err(e) => applog!("overlay", "{why}: fit to monitor {index} failed: {e}"),
    }
}

#[cfg(not(target_os = "macos"))]
fn rect_text(x: i32, y: i32, w: u32, h: u32) -> String {
    format!("{w}x{h}+{x}+{y}")
}

#[cfg(not(target_os = "macos"))]
fn window_rect(window: &WebviewWindow) -> String {
    match (window.outer_position(), window.outer_size()) {
        (Ok(p), Ok(s)) => rect_text(p.x, p.y, s.width, s.height),
        _ => "unknown".into(),
    }
}

#[cfg(not(target_os = "macos"))]
fn primary_index(window: &WebviewWindow) -> usize {
    let (Ok(monitors), Ok(Some(primary))) = (window.available_monitors(), window.primary_monitor()) else {
        return 0;
    };
    monitors
        .iter()
        .position(|m| m.position() == primary.position())
        .unwrap_or(0)
}

#[cfg(not(target_os = "macos"))]
fn monitor_count(window: &WebviewWindow) -> tauri::Result<usize> {
    window.available_monitors().map(|monitors| monitors.len())
}

/// Each monitor's key (monitor_pref::key) in `available_monitors` order, the order `fit_to_monitor` indexes.
#[cfg(not(target_os = "macos"))]
fn monitor_keys(window: &WebviewWindow) -> tauri::Result<Vec<String>> {
    Ok(window
        .available_monitors()?
        .iter()
        .map(|m| {
            let p = m.position();
            monitor_pref::key(m.name().map(String::as_str).unwrap_or(""), p.x as f64, p.y as f64)
        })
        .collect())
}

/// Whether the window no longer covers the work area of the monitor it should be on.
#[cfg(not(target_os = "macos"))]
fn needs_refit(window: &WebviewWindow, index: usize) -> bool {
    let (Ok(monitors), Ok(primary), Ok(pos), Ok(size)) = (
        window.available_monitors(),
        window.primary_monitor(),
        window.outer_position(),
        window.outer_size(),
    ) else {
        return false;
    };
    let Some(m) = monitors.get(index).or(primary.as_ref()).or(monitors.first()) else {
        return false;
    };
    let (x, y, w, h) = overlay_area(m);
    x != pos.x || y != pos.y || w != size.width || h != size.height
}

#[cfg(not(target_os = "macos"))]
fn hit_origin(window: &WebviewWindow) -> tauri::Result<PhysicalPosition<i32>> {
    window.inner_position()
}

/// Windows: read the cursor directly on the hit-test thread without waking the UI main thread.
#[cfg(target_os = "windows")]
fn hit_cursor(_window: &WebviewWindow) -> Option<PhysicalPosition<f64>> {
    use windows_sys::Win32::Foundation::POINT;
    use windows_sys::Win32::UI::WindowsAndMessaging::GetCursorPos;
    let mut pt = POINT { x: 0, y: 0 };
    (unsafe { GetCursorPos(&mut pt) } != 0).then(|| PhysicalPosition::new(pt.x as f64, pt.y as f64))
}

#[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
fn hit_cursor(window: &WebviewWindow) -> Option<PhysicalPosition<f64>> {
    window.cursor_position().ok()
}

#[cfg(target_os = "windows")]
fn overlay_visible(overlay: &Overlay) -> bool {
    let h = overlay.hwnd.load(Ordering::Relaxed);
    if h != 0 {
        use windows_sys::Win32::Foundation::HWND;
        use windows_sys::Win32::UI::WindowsAndMessaging::IsWindowVisible;
        return unsafe { IsWindowVisible(h as HWND) != 0 };
    }
    overlay.visible.load(Ordering::Relaxed)
}

/// Polls in a row with the mouse button up before a stuck drag is dropped (~300 ms).
const DRAG_RELEASE_POLLS: u32 = 10;

/// Whether the primary mouse button is physically held (left, or right when swapped).
#[cfg(target_os = "windows")]
fn primary_button_down() -> bool {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON};
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetSystemMetrics, SM_SWAPBUTTON};
    let key = if unsafe { GetSystemMetrics(SM_SWAPBUTTON) } != 0 { VK_RBUTTON } else { VK_LBUTTON };
    (unsafe { GetAsyncKeyState(key as i32) } as u16 & 0x8000) != 0
}

/// Elsewhere the frontend's pointer-up stays the only way a drag ends.
#[cfg(not(target_os = "windows"))]
fn primary_button_down() -> bool {
    true
}

/// Let the cursor fall through the overlay everywhere except on drawn parts.
/// Polls slowly while nothing can be hit, keeps the shown overlay fitted to its monitor and, on Windows, runs the
/// queued transparency restores (src/transparency.rs).
fn spawn_hit_test(window: WebviewWindow, overlay: Arc<Overlay>) {
    std::thread::spawn(move || {
        let mut ignoring: Option<bool> = None;
        // Times the overlay started taking the mouse since the last summary line.
        let took = Cell::new(0u32);
        let mut set_ignoring = |ignore: bool| {
            if ignoring != Some(ignore) && window.set_ignore_cursor_events(ignore).is_ok() {
                ignoring = Some(ignore);
                overlay.passing.store(ignore, Ordering::Relaxed);
                if !ignore {
                    took.set(took.get() + 1);
                }
            }
        };
        let mut released_for = 0u32;
        let mut cursor_lost = false;
        let mut last_refit = Instant::now();
        let mut last_refit_key: Option<String> = None;
        let mut last_summary = Instant::now();
        let mut last_snapshot = Instant::now();
        let mut last_style_check: Option<Instant> = None;
        let mut style_mismatch: Option<Instant> = None;
        let mut style_mismatch_logged = false;
        let mut shown: Option<bool> = None;
        #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
        let mut visible = true;
        #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
        let mut visible_at: Option<Instant> = None;
        #[cfg(not(target_os = "macos"))]
        let mut geometry: Option<(PhysicalPosition<i32>, f64)> = None;
        #[cfg(target_os = "macos")]
        let mut mac_geometry = overlay_macos::read_geometry(&window).ok();
        let mut pause = HIT_TEST_INTERVAL;
        let mut last_cursor: Option<(f64, f64)> = None;
        let mut still_since = Instant::now();
        loop {
            // The style the pet window really has, against what the hit test last set: if they stay
            // apart, clicks land where the hit test thinks they pass (or the other way round).
            if last_style_check.is_none_or(|t| t.elapsed() >= STYLE_CHECK_INTERVAL) {
                last_style_check = Some(Instant::now());
                let set = overlay.passing.load(Ordering::Relaxed);
                match diag::overlay_passes() {
                    Some(actual) if actual != set => {
                        let since = *style_mismatch.get_or_insert_with(Instant::now);
                        if !style_mismatch_logged && since.elapsed() >= STYLE_MISMATCH_GRACE {
                            style_mismatch_logged = true;
                            applog!(
                                "overlay",
                                "pet window {} the mouse but the hit test set it to {}; {}",
                                if actual { "passes" } else { "takes" },
                                if set { "pass" } else { "take" },
                                diag::under_cursor()
                            );
                        }
                    }
                    _ => {
                        if style_mismatch_logged {
                            applog!("overlay", "pet window style matches the hit test again");
                        }
                        style_mismatch = None;
                        style_mismatch_logged = false;
                    }
                }
            }
            if last_summary.elapsed() >= HIT_SUMMARY_INTERVAL {
                last_summary = Instant::now();
                let n = took.replace(0);
                if n > 0 {
                    applog!("overlay", "took the mouse {n} times in the last minute");
                }
            }
            #[cfg(target_os = "windows")]
            let visible = overlay_visible(&overlay);
            #[cfg(target_os = "macos")]
            let mut visible = overlay.visible.load(Ordering::Relaxed);
            #[cfg(target_os = "macos")]
            if !visible {
                if let Some((_, win_num)) = mac_geometry {
                    // Thread-safe CoreGraphics check spots `hotkey.rs` showing the window without waking the UI thread.
                    if overlay_macos::window_onscreen(win_num) == Some(true)
                        && window.is_visible().unwrap_or(false)
                    {
                        overlay.visible.store(true, Ordering::Relaxed);
                        visible = true;
                    }
                }
            }
            #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
            if visible_at.is_none_or(|at| at.elapsed() >= HIT_VISIBLE_INTERVAL) {
                visible = window.is_visible().unwrap_or(true);
                visible_at = Some(Instant::now());
            }
            let came_back = shown == Some(false) && visible;
            // The page stops drawing and drops its room subscriptions while the pet is hidden (stores/activity.ts).
            if shown != Some(visible) {
                shown = Some(visible);
                let _ = window.emit_to("main", "window:visible", visible);
            }
            // A hidden overlay keeps its place until it is shown again, and is fitted at once then: a full-screen
            // game flips the work area and scale while it runs, and each resize gives the window a new surface.
            if visible && (came_back || last_refit.elapsed() >= REFIT_INTERVAL) {
                last_refit = Instant::now();
                let index = overlay.monitor.lock().map(|m| *m).unwrap_or(0);
                #[cfg(target_os = "macos")]
                let refit = overlay_macos::check_refit(&window, index)
                    .is_some_and(|(actual_visible, needs, geom, win_num)| {
                        mac_geometry = Some((geom, win_num));
                        if !actual_visible {
                            overlay.visible.store(false, Ordering::Relaxed);
                            visible = false;
                            if shown != Some(false) {
                                shown = Some(false);
                                let _ = window.emit_to("main", "window:visible", false);
                            }
                        }
                        actual_visible && needs
                    });
                #[cfg(not(target_os = "macos"))]
                let refit = needs_refit(&window, index);
                if refit {
                    overlay.moved.store(true, Ordering::Relaxed);
                    let was = window_rect(&window);
                    // A refit that does not stick repeats on every check: log it once, not every 2 s.
                    let key = format!("{index} {was}");
                    if last_refit_key.as_deref() != Some(key.as_str()) {
                        fit_and_log(&window, index, &format!("refit from {was}"));
                        last_refit_key = Some(key);
                    } else {
                        let _ = fit_to_monitor(&window, index);
                    }
                }
            }
            #[cfg(target_os = "windows")]
            if let Some(why) = transparency::due() {
                transparency::restore(&window, &why);
            }
            let idle = !visible || overlay.hit.lock().map(|st| st.inert()).unwrap_or(false);
            if idle {
                set_ignoring(true);
                std::thread::sleep(HIT_TEST_IDLE_INTERVAL);
                continue;
            }
            std::thread::sleep(pause);
            #[cfg(target_os = "macos")]
            let sample: Option<(PhysicalPosition<f64>, PhysicalPosition<i32>, f64)> = {
                if overlay.moved.swap(false, Ordering::Relaxed) {
                    mac_geometry = None;
                }
                if mac_geometry.is_none() {
                    mac_geometry = overlay_macos::read_geometry(&window).ok();
                }
                mac_geometry.and_then(|(geom, _)| {
                    overlay_macos::hit_cursor_cached(geom)
                        .map(|cursor| (cursor, PhysicalPosition::new(0, 0), geom.scale))
                })
            };
            #[cfg(not(target_os = "macos"))]
            let sample: Option<(PhysicalPosition<f64>, PhysicalPosition<i32>, f64)> = {
                if overlay.moved.swap(false, Ordering::Relaxed) {
                    geometry = None;
                }
                if geometry.is_none() {
                    geometry = match (hit_origin(&window), window.scale_factor()) {
                        (Ok(origin), Ok(scale)) => Some((origin, scale)),
                        _ => None,
                    };
                }
                match (hit_cursor(&window), geometry) {
                    (Some(cursor), Some((origin, scale))) => Some((cursor, origin, scale)),
                    _ => None,
                }
            };
            let Some((cursor, origin, scale)) = sample else {
                // No cursor (lock screen, UAC, remote desktop): let clicks through rather than
                // keep whatever was last decided, which could leave the whole screen unclickable.
                if !cursor_lost {
                    cursor_lost = true;
                    applog!("overlay", "cursor unavailable, letting clicks through; {}", diag::foreground());
                }
                set_ignoring(true);
                continue;
            };
            if cursor_lost {
                cursor_lost = false;
                applog!("overlay", "cursor available again");
            }
            if last_cursor != Some((cursor.x, cursor.y)) {
                last_cursor = Some((cursor.x, cursor.y));
                still_since = Instant::now();
            }
            pause = if still_since.elapsed() >= HIT_TEST_STILL_AFTER { HIT_TEST_STILL_INTERVAL } else { HIT_TEST_INTERVAL };
            // A drag whose pointer-up never reached the frontend (webview hung, capture lost)
            // must not keep the full-screen overlay taking every click.
            let snapshot = applog::DEBUG && last_snapshot.elapsed() >= HIT_SNAPSHOT_INTERVAL;
            let (ignore, state) = match overlay.hit.lock() {
                Ok(mut st) => {
                    if st.dragging {
                        // The button check below counts polls at the fast pace.
                        pause = HIT_TEST_INTERVAL;
                        if !primary_button_down() {
                            released_for += 1;
                            if released_for >= DRAG_RELEASE_POLLS {
                                st.dragging = false;
                                released_for = 0;
                                applog!("overlay", "drag ended by the button check: the page missed the pointer-up");
                            }
                        } else {
                            released_for = 0;
                        }
                    } else {
                        released_for = 0;
                    }
                    (
                        !st.interactive((cursor.x, cursor.y), (origin.x as f64, origin.y as f64), scale),
                        snapshot.then(|| {
                            format!(
                                "{} hit rects, page scale {}, dragging {}",
                                st.rects.len(),
                                st.page_scale.map_or_else(|| "not reported".to_string(), |s| s.to_string()),
                                st.dragging
                            )
                        }),
                    )
                }
                Err(_) => continue,
            };
            set_ignoring(ignore);
            if let Some(state) = state {
                last_snapshot = Instant::now();
                debuglog!(
                    "hit",
                    "cursor ({:.0},{:.0}), window origin ({},{}), window scale {scale}, {state}; wants the mouse: {}; \
                     style passes: {:?}; {}",
                    cursor.x,
                    cursor.y,
                    origin.x,
                    origin.y,
                    !ignore,
                    diag::overlay_passes(),
                    diag::under_cursor()
                );
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Before any window or hook: exit when another instance is running (Windows), restart
    // through UAC when the player chose to run as administrator.
    let (instance, startup) = elevation::startup();
    let overlay = Arc::new(Overlay::default());
    let builder = tauri::Builder::default();
    // WebKit needs byte ranges to play the bundled card videos (src/media.rs).
    #[cfg(target_os = "macos")]
    let builder = builder.register_asynchronous_uri_scheme_protocol("tauri", media::serve);
    let builder = builder.plugin(tauri_plugin_process::init());
    #[cfg(feature = "updater")]
    let builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    builder
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_notification::init())
        .manage(overlay.clone())
        .invoke_handler(tauri::generate_handler![
            set_click_through,
            set_always_on_top,
            set_hit_regions,
            set_dragging,
            set_popup_open,
            set_mouse_active,
            open_panel,
            set_panel_scale,
            watch_second_start,
            toggle_panel,
            show_panel,
            hide_panel,
            #[cfg(not(feature = "standalone"))]
            open_race,
            #[cfg(not(feature = "standalone"))]
            show_race,
            #[cfg(not(feature = "standalone"))]
            close_race,
            open_ddz,
            show_ddz,
            close_ddz,
            open_todo,
            show_todo,
            hide_todo,
            set_todo_on_top,
            set_capture_window,
            open_about_link,
            export_log,
            log_tail,
            debug_log,
            admin_status,
            set_run_as_admin,
            autostart::autostart_status,
            autostart::set_autostart,
            write_log,
            notify,
            access::input_access_missing,
            access::open_input_settings,
            hotkey::set_hotkey,
            #[cfg(feature = "updater")]
            update::install_version
        ])
        .on_window_event(|window, event| {
            if window.label() == "main" && matches!(
                event,
                tauri::WindowEvent::Moved(_) | tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. }
            ) {
                window.state::<Arc<Overlay>>().moved.store(true, Ordering::Relaxed);
            }
            if window.label() == "panel" {
                match event {
                    tauri::WindowEvent::CloseRequested { api, .. } => {
                        api.prevent_close();
                        if window.hide().is_ok() {
                            panel_hidden();
                        }
                        let _ = window.emit("panel:visible", false);
                    }
                    tauri::WindowEvent::Destroyed => PANEL_VISIBLE.store(false, Ordering::Relaxed),
                    // Moved to a monitor of another scale: the window keeps its logical size, the page its zoom,
                    // until the move ends (`panel_moved`).
                    tauri::WindowEvent::ScaleFactorChanged { .. } => {
                        if let Some(panel) = window.app_handle().get_webview_window("panel") {
                            zoom_panel(&panel, PANEL_ZOOM.lock().map(|z| *z).unwrap_or(1.0));
                        }
                    }
                    tauri::WindowEvent::Moved(_) => panel_moved(window.app_handle()),
                    _ => {}
                }
            }
            if window.label() == "todo" {
                match event {
                    tauri::WindowEvent::CloseRequested { api, .. } => {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                    tauri::WindowEvent::Moved(pos) => {
                        let _ = window.emit_to("main", "todo:moved", (pos.x, pos.y));
                    }
                    _ => {}
                }
            }
            // However the table's window went (its close key, the desk, the system), the desk stops sending to it.
            if window.label() == "ddz" {
                if let tauri::WindowEvent::Destroyed = event {
                    DDZ_OPEN.store(false, Ordering::Relaxed);
                    applog!("ddz", "closed");
                    // From the app: the window's own handle is going away.
                    let _ = window.app_handle().emit_to("main", "ddz:closed", ());
                }
            }
            if window.label() == "capture" {
                match event {
                    tauri::WindowEvent::CloseRequested { .. } => {
                        CAPTURE_OPEN.store(false, Ordering::Relaxed);
                        applog!("capture", "closed from its title bar");
                        let _ = window.emit_to("main", "capture:closed", ());
                    }
                    tauri::WindowEvent::Destroyed => {
                        CAPTURE_OPEN.store(false, Ordering::Relaxed);
                    }
                    // A minimized window reports no size; that one is not kept.
                    tauri::WindowEvent::Resized(size) => {
                        let size = size.to_logical::<f64>(window.scale_factor().unwrap_or(1.0));
                        if size.width >= 160.0 && size.height >= 160.0 {
                            let _ = window.emit_to("main", "capture:size", (size.width, size.height));
                        }
                    }
                    _ => {}
                }
            }
        })
        .setup(move |app| {
            // ---- exportable log, first so everything after it is recorded ----
            if let Ok(dir) = app.path().app_log_dir() {
                applog::init(dir);
            }
            let previous_hook = std::panic::take_hook();
            std::panic::set_hook(Box::new(move |info| {
                let thread = std::thread::current();
                let location = info
                    .location()
                    .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
                    .unwrap_or_else(|| "unknown location".into());
                let payload = info.payload();
                let message = payload
                    .downcast_ref::<&str>()
                    .map(|s| s.to_string())
                    .or_else(|| payload.downcast_ref::<String>().cloned())
                    .unwrap_or_else(|| "non-text panic".into());
                applog::write_now(
                    "panic",
                    &format!("thread '{}' at {location}: {message}", thread.name().unwrap_or("unnamed")),
                );
                previous_hook(info);
            }));
            let admin = match diag::elevated() {
                Some(true) => "as admin",
                Some(false) => "not as admin",
                None => "admin unknown",
            };
            let build = if applog::DEBUG {
                format!(", debug build {}", option_env!("ASOULTAPPO_BUILD").unwrap_or("local"))
            } else {
                String::new()
            };
            applog!("app", "{} {} on {}, {admin}{build}", edition::PRODUCT_NAME, app.package_info().version, diag::os_version());
            match &startup {
                elevation::Startup::Normal if elevation::run_as_admin() => applog!("app", "start as administrator is on"),
                elevation::Startup::Normal => {}
                elevation::Startup::CannotElevate => {
                    applog!("app", "start as administrator is on, but this account cannot run as administrator")
                }
                elevation::Startup::Declined(e) => applog!("app", "start as administrator is on, but UAC was not granted: {e}"),
            }
            match &instance {
                elevation::Instance::Only => {}
                elevation::Instance::AfterWait(waited) => {
                    applog!("app", "waited {} ms for the previous instance to exit", waited.as_millis())
                }
                elevation::Instance::Unchecked(e) => applog!("app", "single-instance check failed ({e}); running without it"),
            }
            autostart::refresh();
            match tauri::webview_version() {
                Ok(v) => applog!("app", "webview {v}"),
                Err(e) => applog!("app", "webview version unavailable: {e}"),
            }

            // ---- overlay window over the work area, mouse passes through until something is hit ----
            if let Some(w) = main_window(app.handle()) {
                // `focus: false` only controls initial focus. Keep clicks on the Windows
                // overlay from activating it over a game or hardware-accelerated video.
                // This maps to WS_EX_NOACTIVATE; the separate panel stays focusable.
                #[cfg(target_os = "windows")]
                if let Err(e) = w.set_focusable(false) {
                    applog!("overlay", "set_focusable(false) failed: {e}");
                }
                // While the cursor is on a pet the overlay is opaque to the mouse; as a tool window it
                // still doesn't count as covering a browser, which would stop drawing (src/tool_window.rs).
                #[cfg(target_os = "windows")]
                if let Ok(hwnd) = w.hwnd() {
                    let raw = hwnd.0 as isize;
                    diag::set_overlay(raw);
                    overlay.hwnd.store(raw, Ordering::Relaxed);
                }
                #[cfg(target_os = "windows")]
                match tool_window::keep(&w) {
                    Ok(true) => {}
                    Ok(false) => applog!("overlay", "tool window subclass not installed"),
                    Err(e) => applog!("overlay", "tool window subclass failed: {e}"),
                }
                // A full-screen game can leave the overlay black over the desktop: its web view's failures are
                // logged and its transparency is set again after them (src/transparency.rs).
                #[cfg(target_os = "windows")]
                transparency::watch_process_failures(&w);
                #[cfg(target_os = "macos")]
                join_all_spaces(&w, "overlay");
                // The monitor last picked from the tray, while it is plugged in; else the primary one.
                let saved = monitor_pref::load(app.handle())
                    .and_then(|key| monitor_keys(&w).ok().and_then(|keys| monitor_pref::pick(&keys, &key)));
                let index = saved.unwrap_or_else(|| primary_index(&w));
                if saved.is_some() {
                    applog!("overlay", "start on the monitor picked last time");
                }
                if let Ok(mut m) = overlay.monitor.lock() {
                    *m = index;
                }
                let count = monitor_count(&w).unwrap_or(0);
                fit_and_log(&w, index, &format!("start, {count} monitor(s)"));
                let _ = w.set_ignore_cursor_events(true);
                if let Err(e) = w.show() {
                    applog!("overlay", "show failed: {e}");
                }
                overlay.visible.store(true, Ordering::Relaxed);
                spawn_hit_test(w, overlay.clone());
                diag::spawn_foreground_watch();
                elevation::spawn_watch(app.handle().clone());
                access::spawn_watch(app.handle().clone());
            } else {
                applog!("overlay", "main window missing");
            }

            // ---- tray ----
            let toggle_visible =
                MenuItem::with_id(app, "toggle_visible", "显示 / 隐藏桌宠", true, None::<&str>)?;
            let panel = MenuItem::with_id(app, "toggle_panel", "打开 / 关闭面板", true, None::<&str>)?;
            let pomodoro = MenuItem::with_id(app, "toggle_pomodoro", "开始 / 结束番茄钟", true, None::<&str>)?;
            let capture = MenuItem::with_id(app, "toggle_capture", "打开 / 关闭采集窗口", true, None::<&str>)?;
            let click_through =
                MenuItem::with_id(app, "toggle_click_through", "切换点击穿透", true, None::<&str>)?;
            let reset = MenuItem::with_id(app, "reset_position", "桌宠放回右下角", true, None::<&str>)?;
            let next_monitor =
                MenuItem::with_id(app, "next_monitor", "换到下一个显示器", true, None::<&str>)?;
            let export = MenuItem::with_id(app, "export_log", "导出运行日志", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(
                app,
                &[&toggle_visible, &panel, &pomodoro, &capture, &click_through, &reset, &next_monitor, &export, &quit],
            )?;

            let tray_overlay = overlay.clone();
            let mut tray = TrayIconBuilder::new()
                .tooltip(edition::DISPLAY_NAME)
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "toggle_visible" => {
                        if let Some(w) = main_window(app) {
                            if w.is_visible().unwrap_or(true) {
                                applog!("tray", "hide pet");
                                let _ = w.hide();
                                tray_overlay.visible.store(false, Ordering::Relaxed);
                            } else {
                                applog!("tray", "show pet");
                                let _ = w.show();
                                tray_overlay.visible.store(true, Ordering::Relaxed);
                                #[cfg(target_os = "windows")]
                                transparency::request("shown from the tray");
                            }
                        }
                    }
                    "toggle_panel" => {
                        let _ = app.emit_to("main", "tray", "toggle-panel");
                    }
                    // The entry for a pet docked on the screen's edge, which has no strip and so no strip menu.
                    "toggle_pomodoro" => {
                        let _ = app.emit_to("main", "tray", "toggle-pomodoro");
                    }
                    "toggle_capture" => {
                        let _ = app.emit_to("main", "tray", "toggle-capture");
                    }
                    "toggle_click_through" => {
                        // Flip it here too, so the tray still frees the screen when the page is hung;
                        // the page flips its setting from the same old value and ends up agreeing.
                        if let Ok(mut st) = tray_overlay.hit.lock() {
                            st.click_through = !st.click_through;
                            st.dragging = false;
                            applog!("tray", "click-through {}", on_off(st.click_through));
                        }
                        let _ = app.emit_to("main", "tray", "toggle-click-through");
                    }
                    "reset_position" => {
                        applog!("tray", "reset pet position");
                        if let Some(w) = main_window(app) {
                            let _ = w.show();
                            tray_overlay.visible.store(true, Ordering::Relaxed);
                        }
                        let _ = app.emit_to("main", "tray", "reset-position");
                    }
                    "next_monitor" => move_to_next_monitor(app, &tray_overlay, "tray", false),
                    // Here too: when the pet window blocks clicks the panel may be unreachable.
                    "export_log" => {
                        let overlay = tray_overlay.clone();
                        let app = app.clone();
                        tauri::async_runtime::spawn_blocking(move || {
                            log_state(&overlay, "export from the tray");
                            let _ = export_log_files(&app);
                        });
                    }
                    "quit" => {
                        applog!("tray", "quit");
                        app.exit(0)
                    }
                    _ => {}
                });
            // Windows: a left click opens the panel the way the Dock icon does on macOS, a right click pops the menu.
            // A runtime check rather than #[cfg], so the handler is type-checked on every platform.
            if cfg!(target_os = "windows") {
                tray = tray.show_menu_on_left_click(false).on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        applog!("tray", "left click: raise panel");
                        // On the page it shows, like the desk's menu key.
                        let _ = tray.app_handle().emit_to("main", "tray", "raise-panel");
                    }
                });
            }
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            // ---- global input hook (counts / deltas only) ----
            let handle = app.handle().clone();
            let input_overlay = overlay.clone();
            // Debug build: when the last click line was written, and clicks skipped since.
            let click_log: Mutex<(Option<Instant>, u32)> = Mutex::new((None, 0));
            let mouse_pulse: Mutex<Option<Instant>> = Mutex::new(None);
            input::spawn_hook(move |heard| {
                let down = matches!(heard.event, input::InputEvent::MouseDown { .. });
                let passing = input_overlay.passing.load(Ordering::Relaxed);
                // A press that fell through the overlay landed on another window. The Windows overlay
                // never takes focus, so the desk gets no blur for it and is told here instead.
                if down && passing && should_emit_outside_click() {
                    let _ = handle.emit_to("main", "outside-click", ());
                }
                if applog::DEBUG && down {
                    if let Ok(mut c) = click_log.lock() {
                        if c.0.is_none_or(|t| t.elapsed() >= Duration::from_secs(1)) {
                            let skipped = std::mem::take(&mut c.1);
                            c.0 = Some(Instant::now());
                            debuglog!(
                                "click",
                                "{}; hit test set the pet window to {} ({skipped} more clicks since the last line)",
                                diag::under_cursor(),
                                if passing { "pass" } else { "take the mouse" }
                            );
                        } else {
                            c.1 += 1;
                        }
                    }
                }
                if matches!(heard.event, input::InputEvent::MouseMove { .. }) && !should_emit_mouse_move() {
                    // Keep the main desk's room-away, idle-wake and reminder clocks aware of mouse use at <= 1 Hz.
                    let pulse = mouse_pulse.lock().map(|mut t| allow_mouse_pulse(&mut t, Instant::now())).unwrap_or(false);
                    if pulse && handle.emit_to("main", "input", heard).is_err() {
                        input::note_emit_failure();
                    }
                    return;
                }
                // Both windows listen: the desk pet, and the panel's preview pet on the emote and room pages.
                if handle.emit("input", heard).is_err() {
                    input::note_emit_failure();
                }
            });
            // Background controller input: Windows XInput and PS4/PS5 HID on Windows/macOS.
            let pad_handle = app.handle().clone();
            gamepad::spawn_poller(move |ev| {
                let _ = pad_handle.emit("input", input::HeardInput { event: ev, injected: None });
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running AsoulTappo")
        .run(|_app, _event| {
            // macOS: a click on the Dock icon, or opening the app again, brings up the panel on the page it shows; the
            // pet window itself has nothing to show.
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen { .. } = _event {
                applog!("tray", "dock icon: raise panel");
                let _ = _app.emit_to("main", "tray", "raise-panel");
            }
        });
}

#[cfg(all(test, target_os = "macos"))]
mod page_zoom_tests {
    use super::*;

    #[test]
    fn this_webkit_answers_whether_it_zooms_pages() {
        // macOS 11 and later have `setPageZoom:`; this machine is one of them.
        assert!(page_zoom_supported());
        assert!(page_zoom_supported());
        // The runtime's answer is about the selector asked for, not any.
        use objc2::{runtime::AnyClass, sel};
        assert!(!AnyClass::get(c"WKWebView").unwrap().responds_to(sel!(setPageZoomThatIsNotThere:)));
    }

    #[test]
    fn a_window_is_not_taken_for_dragged_with_no_button_down() {
        // Nobody holds the mouse while the tests run.
        assert!(!window_drag_held());
    }
}

#[cfg(test)]
mod heard_input_tests {
    use super::*;

    #[test]
    fn outside_click_is_sent_until_the_desk_reports_and_while_a_popup_is_open() {
        assert!(outside_click_allowed(false, false));
        assert!(!outside_click_allowed(true, false));
        assert!(outside_click_allowed(true, true));
    }

    #[test]
    fn mouse_pulses_are_at_least_one_second_apart() {
        let mut last = None;
        let start = Instant::now();
        assert!(allow_mouse_pulse(&mut last, start));
        assert!(!allow_mouse_pulse(&mut last, start + Duration::from_millis(999)));
        assert!(allow_mouse_pulse(&mut last, start + Duration::from_secs(1)));
    }

    #[test]
    fn mouse_moves_are_broadcast_only_while_a_window_uses_them() {
        // Main, panel visible, panel preview active, capture, table, expected broadcast.
        for (main, panel, preview, capture, table, broadcast) in [
            (false, false, false, false, false, false),
            (true,  false, false, false, false, true),
            (false, true,  true,  false, false, true),
            (false, false, false, true,  false, true),
            (false, false, false, false, true,  true),
            (false, true,  false, false, false, false),
            (false, false, true,  false, false, false),
            (true,  true,  true,  true,  true,  true),
        ] {
            assert_eq!(mouse_move_allowed(false, main, panel, preview, capture, table), broadcast);
            assert!(!mouse_move_allowed(true, main, panel, preview, capture, table));
        }
    }

    #[test]
    fn the_page_is_told_who_sent_an_input_edge_when_the_hook_can_tell() {
        let json = |event, injected| serde_json::to_value(input::HeardInput { event, injected }).unwrap();
        assert_eq!(json(input::InputEvent::KeyDown, None), serde_json::json!({ "kind": "key_down" }));
        assert_eq!(
            json(input::InputEvent::KeyDown, Some(true)),
            serde_json::json!({ "kind": "key_down", "injected": true })
        );
        assert_eq!(
            json(input::InputEvent::KeyUp, Some(true)),
            serde_json::json!({ "kind": "key_up", "injected": true })
        );
        assert_eq!(
            json(input::InputEvent::MouseDown { button: input::MouseButton::Left }, Some(false)),
            serde_json::json!({ "kind": "mouse_down", "button": "left", "injected": false })
        );
    }
}
