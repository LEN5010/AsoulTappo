mod gamepad;
mod hit;
mod input;
mod update;

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
/// How often the overlay checks that it still covers its monitor's work area
/// (monitor plugged/unplugged, resolution, scaling or taskbar changed).
const REFIT_INTERVAL: Duration = Duration::from_secs(2);

#[derive(Default)]
struct Overlay {
    hit: Mutex<HitState>,
    /// Index into `available_monitors()` of the monitor the overlay covers.
    monitor: Mutex<usize>,
}

fn main_window(app: &tauri::AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

/// Click-through: the overlay never takes the mouse (turn it off from the tray menu).
#[tauri::command]
fn set_click_through(overlay: tauri::State<'_, Arc<Overlay>>, enabled: bool) {
    if let Ok(mut st) = overlay.hit.lock() {
        st.click_through = enabled;
    }
}

#[tauri::command]
fn set_always_on_top(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    if let Some(window) = main_window(&app) {
        window.set_always_on_top(enabled).map_err(|e| e.to_string())?;
    }
    Ok(())
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
        .map_err(|e| e.to_string())?;
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

/// Links the About section may open in the system browser or mail app.
const ABOUT_LINKS: [&str; 4] = [
    "https://github.com/LEN5010/AsoulTappo",
    "https://space.bilibili.com/107261543",
    "mailto:len5010@qq.com",
    "https://len5010.top/dynamics/download?app=tappo",
];

#[tauri::command]
fn open_about_link(url: String) -> Result<(), String> {
    if !ABOUT_LINKS.contains(&url.as_str()) {
        return Err("unknown link".into());
    }
    #[cfg(target_os = "windows")]
    let result = std::process::Command::new("rundll32").args(["url.dll,FileProtocolHandler", &url]).spawn();
    #[cfg(target_os = "macos")]
    let result = std::process::Command::new("open").arg(&url).spawn();
    #[cfg(all(unix, not(target_os = "macos")))]
    let result = std::process::Command::new("xdg-open").arg(&url).spawn();
    result.map(|_| ()).map_err(|e| e.to_string())
}

/// Areas (CSS px) where the overlay draws something and should take the mouse.
#[tauri::command]
fn set_hit_regions(overlay: tauri::State<'_, Arc<Overlay>>, rects: Vec<HitRect>) {
    if let Ok(mut st) = overlay.hit.lock() {
        st.rects = rects;
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
/// an unknown index falls back to the primary monitor.
fn fit_to_monitor(window: &WebviewWindow, index: usize) -> tauri::Result<()> {
    let monitors = window.available_monitors()?;
    let primary = window.primary_monitor()?;
    if let Some(m) = monitors.get(index).or(primary.as_ref()).or(monitors.first()) {
        let area = m.work_area();
        window.set_position(PhysicalPosition::new(area.position.x, area.position.y))?;
        window.set_size(PhysicalSize::new(area.size.width, area.size.height))?;
    }
    Ok(())
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
    let area = m.work_area();
    area.position.x != pos.x
        || area.position.y != pos.y
        || area.size.width != size.width
        || area.size.height != size.height
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
        let mut released_for = 0u32;
        let mut last_refit = Instant::now();
        loop {
            if last_refit.elapsed() >= REFIT_INTERVAL {
                last_refit = Instant::now();
                let index = overlay.monitor.lock().map(|m| *m).unwrap_or(0);
                if needs_refit(&window, index) {
                    let _ = fit_to_monitor(&window, index);
                }
            }
            let idle = !window.is_visible().unwrap_or(true)
                || overlay.hit.lock().map(|st| st.click_through).unwrap_or(false);
            if idle {
                if ignoring != Some(true) && window.set_ignore_cursor_events(true).is_ok() {
                    ignoring = Some(true);
                }
                std::thread::sleep(HIT_TEST_IDLE_INTERVAL);
                continue;
            }
            std::thread::sleep(HIT_TEST_INTERVAL);
            let (Ok(cursor), Ok(origin), Ok(scale)) =
                (window.cursor_position(), window.inner_position(), window.scale_factor())
            else {
                // No cursor (lock screen, UAC, remote desktop): let clicks through rather than
                // keep whatever was last decided, which could leave the whole screen unclickable.
                if ignoring != Some(true) && window.set_ignore_cursor_events(true).is_ok() {
                    ignoring = Some(true);
                }
                continue;
            };
            // A drag whose pointer-up never reached the frontend (webview hung, capture lost)
            // must not keep the full-screen overlay taking every click.
            if let Ok(mut st) = overlay.hit.lock() {
                if st.dragging && !primary_button_down() {
                    released_for += 1;
                    if released_for >= DRAG_RELEASE_POLLS {
                        st.dragging = false;
                        released_for = 0;
                    }
                } else {
                    released_for = 0;
                }
            }
            let ignore = match overlay.hit.lock() {
                Ok(st) => !st.interactive((cursor.x, cursor.y), (origin.x as f64, origin.y as f64), scale),
                Err(_) => continue,
            };
            if ignoring != Some(ignore) && window.set_ignore_cursor_events(ignore).is_ok() {
                ignoring = Some(ignore);
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let overlay = Arc::new(Overlay::default());
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
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
            open_about_link,
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
        })
        .setup(move |app| {
            // ---- overlay window over the work area, mouse passes through until something is hit ----
            if let Some(w) = main_window(app.handle()) {
                // `focus: false` only controls initial focus. Keep clicks on the Windows
                // overlay from activating it over a game or hardware-accelerated video.
                // This maps to WS_EX_NOACTIVATE; the separate panel stays focusable.
                #[cfg(target_os = "windows")]
                let _ = w.set_focusable(false);
                let index = primary_index(&w);
                if let Ok(mut m) = overlay.monitor.lock() {
                    *m = index;
                }
                let _ = fit_to_monitor(&w, index);
                let _ = w.set_ignore_cursor_events(true);
                let _ = w.show();
                spawn_hit_test(w, overlay.clone());
            }

            // ---- tray ----
            let toggle_visible =
                MenuItem::with_id(app, "toggle_visible", "显示 / 隐藏桌宠", true, None::<&str>)?;
            let panel = MenuItem::with_id(app, "toggle_panel", "打开 / 关闭面板", true, None::<&str>)?;
            let click_through =
                MenuItem::with_id(app, "toggle_click_through", "切换点击穿透", true, None::<&str>)?;
            let reset = MenuItem::with_id(app, "reset_position", "桌宠放回右下角", true, None::<&str>)?;
            let next_monitor =
                MenuItem::with_id(app, "next_monitor", "换到下一个显示器", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(
                app,
                &[&toggle_visible, &panel, &click_through, &reset, &next_monitor, &quit],
            )?;

            let tray_overlay = overlay.clone();
            let mut tray = TrayIconBuilder::new()
                .tooltip("AsoulTappo")
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "toggle_visible" => {
                        if let Some(w) = main_window(app) {
                            if w.is_visible().unwrap_or(true) {
                                let _ = w.hide();
                            } else {
                                let _ = w.show();
                            }
                        }
                    }
                    "toggle_panel" => {
                        let _ = app.emit_to("main", "tray", "toggle-panel");
                    }
                    "toggle_click_through" => {
                        // Flip it here too, so the tray still frees the screen when the page is hung;
                        // the page flips its setting from the same old value and ends up agreeing.
                        if let Ok(mut st) = tray_overlay.hit.lock() {
                            st.click_through = !st.click_through;
                            st.dragging = false;
                        }
                        let _ = app.emit_to("main", "tray", "toggle-click-through");
                    }
                    "reset_position" => {
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
                                let _ = fit_to_monitor(&w, *m);
                            }
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            // ---- global input hook (counts / deltas only) ----
            let handle = app.handle().clone();
            input::spawn_hook(move |ev| {
                // Both windows listen: the desk pet, and the panel's preview pet on the emote and room pages.
                let _ = handle.emit("input", ev);
            });
            // Controller presses feed the pet like key presses (Windows/XInput; works under fullscreen games).
            let pad_handle = app.handle().clone();
            gamepad::spawn_poller(move |ev| {
                let _ = pad_handle.emit("input", ev);
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AsoulTappo");
}
