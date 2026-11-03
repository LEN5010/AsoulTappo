mod hit;
mod input;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use hit::{HitRect, HitState};
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewWindow,
};

/// How often the cursor is checked against the overlay's hit rectangles.
const HIT_TEST_INTERVAL: Duration = Duration::from_millis(30);

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
fn set_always_on_top(window: WebviewWindow, enabled: bool) -> Result<(), String> {
    window.set_always_on_top(enabled).map_err(|e| e.to_string())
}

/// Areas (CSS px) where the overlay draws something and should take the mouse.
#[tauri::command]
fn set_hit_regions(overlay: tauri::State<'_, Arc<Overlay>>, rects: Vec<HitRect>) {
    if let Ok(mut st) = overlay.hit.lock() {
        st.rects = rects;
    }
}

/// Keep taking the mouse while a pet or the panel is being dragged.
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

/// Let the cursor fall through the overlay everywhere except on drawn parts.
fn spawn_hit_test(window: WebviewWindow, overlay: Arc<Overlay>) {
    std::thread::spawn(move || {
        let mut ignoring: Option<bool> = None;
        loop {
            std::thread::sleep(HIT_TEST_INTERVAL);
            let (Ok(cursor), Ok(origin), Ok(scale)) =
                (window.cursor_position(), window.inner_position(), window.scale_factor())
            else {
                continue;
            };
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
        .manage(overlay.clone())
        .invoke_handler(tauri::generate_handler![
            set_click_through,
            set_always_on_top,
            set_hit_regions,
            set_dragging
        ])
        .setup(move |app| {
            // ---- overlay window over the work area, mouse passes through until something is hit ----
            if let Some(w) = main_window(app.handle()) {
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
                        let _ = app.emit("tray", "toggle-panel");
                    }
                    "toggle_click_through" => {
                        let _ = app.emit("tray", "toggle-click-through");
                    }
                    "reset_position" => {
                        if let Some(w) = main_window(app) {
                            let _ = w.show();
                        }
                        let _ = app.emit("tray", "reset-position");
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
                let _ = handle.emit("input", ev);
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AsoulTappo");
}
