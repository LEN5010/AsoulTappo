#[macro_use]
mod applog;
mod access;
mod diag;
mod elevation;
mod gamepad;
mod hotkey;
mod hit;
mod input;
#[cfg(target_os = "macos")]
mod media;
#[cfg(target_os = "windows")]
mod tool_window;
mod update;

use std::cell::Cell;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use hit::{HitRect, HitState};
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
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
/// How long the hit test trusts what the window last said about being shown, and about where it is and
/// its scale. Each of those questions is answered on the main thread, so asking all of them on every poll
/// keeps the app's event loop busy while nothing changes; only the cursor is read every time.
const HIT_VISIBLE_INTERVAL: Duration = Duration::from_millis(250);
const HIT_GEOMETRY_INTERVAL: Duration = Duration::from_millis(500);
/// How often the overlay checks that it still covers its monitor's work area
/// (monitor plugged/unplugged, resolution, scaling or taskbar changed).
const REFIT_INTERVAL: Duration = Duration::from_secs(2);
/// How often the hit test writes how many times the overlay took the mouse.
const HIT_SUMMARY_INTERVAL: Duration = Duration::from_secs(60);
/// Debug build: how often the hit test writes its full state while the pet can be hit.
const HIT_SNAPSHOT_INTERVAL: Duration = Duration::from_secs(5);
/// How long the pet window's real style may differ from what the hit test set before that is
/// logged (the style is applied on the main thread, a little after the hit test asks).
const STYLE_MISMATCH_GRACE: Duration = Duration::from_secs(1);

#[derive(Default)]
struct Overlay {
    hit: Mutex<HitState>,
    /// Index into `available_monitors()` of the monitor the overlay covers.
    monitor: Mutex<usize>,
    /// The overlay currently lets clicks through, so a mouse press lands on another window.
    passing: AtomicBool,
}

fn main_window(app: &tauri::AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

/// macOS gives a full-screen app a Space of its own. Without these flags the pet stays on the Space it
/// started on and is gone while another desktop or a full-screen app is shown.
#[cfg(target_os = "macos")]
fn join_all_spaces(w: &WebviewWindow) {
    use objc2_app_kit::{NSWindow, NSWindowCollectionBehavior as B};
    match w.ns_window() {
        Ok(ptr) if !ptr.is_null() => {
            // SAFETY: Tauri hands out the window's live NSWindow; setup runs on the main thread.
            let ns = unsafe { &*(ptr as *const NSWindow) };
            ns.setCollectionBehavior(ns.collectionBehavior() | B::CanJoinAllSpaces | B::FullScreenAuxiliary);
            applog!("overlay", "joins all Spaces and full-screen apps");
        }
        Ok(_) => applog!("overlay", "no NSWindow to join all Spaces"),
        Err(e) => applog!("overlay", "join all Spaces failed: {e}"),
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
fn export_log(app: tauri::AppHandle, overlay: tauri::State<'_, Arc<Overlay>>) -> Result<ExportedLog, String> {
    log_state(&overlay, "export from the panel");
    export_log_files(&app)
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

#[tauri::command]
fn show_panel(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("panel") {
        window.unminimize().map_err(|e| e.to_string())?;
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        app.emit_to("panel", "panel:visible", true).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn hide_panel(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("panel") {
        window.hide().map_err(|e| e.to_string())?;
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
        .title("AsoulTappo")
        .inner_size(1000.0, 720.0)
        .min_inner_size(640.0, 480.0)
        .transparent(true)
        .decorations(false)
        .always_on_top(false)
        .skip_taskbar(false)
        .shadow(false)
        .visible(false)
        .focused(false)
        .build()
        .map_err(|e| {
            applog!("panel", "create failed: {e}");
            e.to_string()
        })?;
    applog!("panel", "created");
    if let Some(monitor) = window.current_monitor().map_err(|e| e.to_string())? {
        let area = monitor.work_area();
        let scale = monitor.scale_factor();
        window.set_size(PhysicalSize::new(
            (1000.0 * scale).min(area.size.width as f64 - 20.0) as u32,
            (720.0 * scale).min(area.size.height as f64 - 20.0) as u32,
        )).map_err(|e| e.to_string())?;
    }
    window.center().map_err(|e| e.to_string())?;
    Ok(())
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
        return Ok(());
    }
    if let Some(window) = existing {
        window.unminimize().map_err(|e| e.to_string())?;
        return window.show().map_err(|e| e.to_string());
    }
    let (width, height) = (width.clamp(160.0, 1600.0), height.clamp(160.0, 1600.0));
    let window = WebviewWindowBuilder::new(&app, "capture", WebviewUrl::App("capture.html".into()))
        .title("AsoulTappo 采集窗口")
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
    #[cfg(target_os = "macos")]
    paint_when_covered(&window);
    #[cfg(not(target_os = "macos"))]
    let _ = window;
    Ok(())
}

/// Links the About section may open in the system browser or mail app.
const ABOUT_LINKS: [&str; 6] = [
    "https://github.com/LEN5010/AsoulTappo",
    "https://space.bilibili.com/107261543",
    "mailto:len5010@qq.com",
    "https://len5010.top/dynamics/download?app=tappo",
    "https://len5010.top",
    "https://len5010.top/download",
];

#[tauri::command]
fn open_about_link(url: String) -> Result<(), String> {
    if !ABOUT_LINKS.contains(&url.as_str()) {
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

/// Cover the work area (the monitor minus the taskbar) of monitor `index`;
/// an unknown index falls back to the primary monitor. Returns the area and the
/// monitor's scale factor, for the log.
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

fn rect_text(x: i32, y: i32, w: u32, h: u32) -> String {
    format!("{w}x{h}+{x}+{y}")
}

fn window_rect(window: &WebviewWindow) -> String {
    match (window.outer_position(), window.outer_size()) {
        (Ok(p), Ok(s)) => rect_text(p.x, p.y, s.width, s.height),
        _ => "unknown".into(),
    }
}

fn primary_index(window: &WebviewWindow) -> usize {
    let (Ok(monitors), Ok(Some(primary))) = (window.available_monitors(), window.primary_monitor()) else {
        return 0;
    };
    monitors
        .iter()
        .position(|m| m.position() == primary.position())
        .unwrap_or(0)
}

/// Whether the window no longer covers the work area of the monitor it should be on.
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
/// Polls slowly while nothing can be hit, and keeps the overlay fitted to its monitor.
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
        let mut style_mismatch: Option<Instant> = None;
        let mut style_mismatch_logged = false;
        let mut shown: Option<bool> = None;
        let mut visible = true;
        let mut visible_at: Option<Instant> = None;
        let mut geometry: Option<(PhysicalPosition<i32>, f64)> = None;
        let mut geometry_at = Instant::now();
        let mut pause = HIT_TEST_INTERVAL;
        let mut last_cursor: Option<(f64, f64)> = None;
        let mut still_since = Instant::now();
        loop {
            // The style the pet window really has, against what the hit test last set: if they stay
            // apart, clicks land where the hit test thinks they pass (or the other way round).
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
            if last_refit.elapsed() >= REFIT_INTERVAL {
                last_refit = Instant::now();
                let index = overlay.monitor.lock().map(|m| *m).unwrap_or(0);
                if needs_refit(&window, index) {
                    // The window is about to move: ask where it is again on the next poll.
                    geometry = None;
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
            if last_summary.elapsed() >= HIT_SUMMARY_INTERVAL {
                last_summary = Instant::now();
                let n = took.replace(0);
                if n > 0 {
                    applog!("overlay", "took the mouse {n} times in the last minute");
                }
            }
            if visible_at.is_none_or(|at| at.elapsed() >= HIT_VISIBLE_INTERVAL) {
                visible = window.is_visible().unwrap_or(true);
                visible_at = Some(Instant::now());
            }
            // The page stops drawing and drops its room subscriptions while the pet is hidden (stores/activity.ts).
            if shown != Some(visible) {
                shown = Some(visible);
                let _ = window.emit_to("main", "window:visible", visible);
            }
            let idle = !visible || overlay.hit.lock().map(|st| st.click_through).unwrap_or(false);
            if idle {
                set_ignoring(true);
                std::thread::sleep(HIT_TEST_IDLE_INTERVAL);
                continue;
            }
            std::thread::sleep(pause);
            if geometry.is_none() || geometry_at.elapsed() >= HIT_GEOMETRY_INTERVAL {
                geometry = match (window.inner_position(), window.scale_factor()) {
                    (Ok(origin), Ok(scale)) => Some((origin, scale)),
                    _ => None,
                };
                geometry_at = Instant::now();
            }
            let (Ok(cursor), Some((origin, scale))) = (window.cursor_position(), geometry) else {
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
            if let Ok(mut st) = overlay.hit.lock() {
                if st.dragging {
                    // The button check below counts polls at the fast pace.
                    pause = HIT_TEST_INTERVAL;
                }
                if st.dragging && !primary_button_down() {
                    released_for += 1;
                    if released_for >= DRAG_RELEASE_POLLS {
                        st.dragging = false;
                        released_for = 0;
                        applog!("overlay", "drag ended by the button check: the page missed the pointer-up");
                    }
                } else {
                    released_for = 0;
                }
            }
            let snapshot = applog::DEBUG && last_snapshot.elapsed() >= HIT_SNAPSHOT_INTERVAL;
            let (ignore, state) = match overlay.hit.lock() {
                Ok(st) => (
                    !st.interactive((cursor.x, cursor.y), (origin.x as f64, origin.y as f64), scale),
                    snapshot.then(|| {
                        format!(
                            "{} hit rects, page scale {}, dragging {}",
                            st.rects.len(),
                            st.page_scale.map_or_else(|| "not reported".to_string(), |s| s.to_string()),
                            st.dragging
                        )
                    }),
                ),
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
    builder
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(overlay.clone())
        .invoke_handler(tauri::generate_handler![
            set_click_through,
            set_always_on_top,
            set_hit_regions,
            set_dragging,
            open_panel,
            toggle_panel,
            show_panel,
            hide_panel,
            set_capture_window,
            open_about_link,
            export_log,
            debug_log,
            admin_status,
            set_run_as_admin,
            write_log,
            access::input_access_missing,
            access::open_input_settings,
            hotkey::set_boss_key,
            update::install_version
        ])
        .on_window_event(|window, event| {
            if window.label() == "panel" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                    let _ = window.emit("panel:visible", false);
                }
            }
            if window.label() == "capture" {
                match event {
                    tauri::WindowEvent::CloseRequested { .. } => {
                        applog!("capture", "closed from its title bar");
                        let _ = window.emit_to("main", "capture:closed", ());
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
            applog!("app", "AsoulTappo {} on {}, {admin}{build}", app.package_info().version, diag::os_version());
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
                    diag::set_overlay(hwnd.0 as isize);
                }
                #[cfg(target_os = "windows")]
                match tool_window::keep(&w) {
                    Ok(true) => {}
                    Ok(false) => applog!("overlay", "tool window subclass not installed"),
                    Err(e) => applog!("overlay", "tool window subclass failed: {e}"),
                }
                #[cfg(target_os = "macos")]
                join_all_spaces(&w);
                let index = primary_index(&w);
                if let Ok(mut m) = overlay.monitor.lock() {
                    *m = index;
                }
                let count = w.available_monitors().map(|m| m.len()).unwrap_or(0);
                fit_and_log(&w, index, &format!("start, {count} monitor(s)"));
                let _ = w.set_ignore_cursor_events(true);
                if let Err(e) = w.show() {
                    applog!("overlay", "show failed: {e}");
                }
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
                &[&toggle_visible, &panel, &capture, &click_through, &reset, &next_monitor, &export, &quit],
            )?;

            let tray_overlay = overlay.clone();
            let mut tray = TrayIconBuilder::new()
                .tooltip("AsoulTappo")
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "toggle_visible" => {
                        if let Some(w) = main_window(app) {
                            if w.is_visible().unwrap_or(true) {
                                applog!("tray", "hide pet");
                                let _ = w.hide();
                            } else {
                                applog!("tray", "show pet");
                                let _ = w.show();
                            }
                        }
                    }
                    "toggle_panel" => {
                        let _ = app.emit_to("main", "tray", "toggle-panel");
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
                        }
                        let _ = app.emit_to("main", "tray", "reset-position");
                    }
                    "next_monitor" => {
                        if let Some(w) = main_window(app) {
                            let count = w.available_monitors().map(|m| m.len()).unwrap_or(1).max(1);
                            if let Ok(mut m) = tray_overlay.monitor.lock() {
                                *m = (*m + 1) % count;
                                fit_and_log(&w, *m, &format!("tray next monitor, {count} monitor(s)"));
                            }
                        }
                    }
                    // Here too: when the pet window blocks clicks the panel may be unreachable.
                    "export_log" => {
                        log_state(&tray_overlay, "export from the tray");
                        let _ = export_log_files(app);
                    }
                    "quit" => {
                        applog!("tray", "quit");
                        app.exit(0)
                    }
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            // ---- global input hook (counts / deltas only) ----
            let handle = app.handle().clone();
            let input_overlay = overlay.clone();
            // Debug build: when the last click line was written, and clicks skipped since.
            let click_log: Mutex<(Option<Instant>, u32)> = Mutex::new((None, 0));
            input::spawn_hook(move |ev| {
                let down = matches!(ev, input::InputEvent::MouseDown { .. });
                let passing = input_overlay.passing.load(Ordering::Relaxed);
                // A press that fell through the overlay landed on another window. The Windows overlay
                // never takes focus, so the desk gets no blur for it and is told here instead.
                if down && passing {
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
                // Both windows listen: the desk pet, and the panel's preview pet on the emote and room pages.
                if handle.emit("input", ev).is_err() {
                    input::note_emit_failure();
                }
            });
            // Controller presses feed the pet like key presses (Windows/XInput; works under fullscreen games).
            let pad_handle = app.handle().clone();
            gamepad::spawn_poller(move |ev| {
                let _ = pad_handle.emit("input", ev);
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running AsoulTappo")
        .run(|_app, _event| {
            // macOS: a click on the Dock icon opens the panel, the pet window itself has nothing to show.
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen { .. } = _event {
                applog!("tray", "dock icon: open panel");
                let _ = _app.emit_to("main", "tray", "open-panel");
            }
        });
}
