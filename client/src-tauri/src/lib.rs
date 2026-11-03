mod input;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, PhysicalPosition, WebviewWindow,
};

fn main_window(app: &tauri::AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

/// Toggle mouse click-through for the pet window. When enabled the window
/// ignores the cursor entirely; use the tray menu to turn it off again.
#[tauri::command]
fn set_click_through(window: WebviewWindow, enabled: bool) -> Result<(), String> {
    window.set_ignore_cursor_events(enabled).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_always_on_top(window: WebviewWindow, enabled: bool) -> Result<(), String> {
    window.set_always_on_top(enabled).map_err(|e| e.to_string())
}

/// Resize the (transparent, frameless) window to fit its content (logical px).
#[tauri::command]
fn resize_window(window: WebviewWindow, width: f64, height: f64) -> Result<(), String> {
    let w = width.clamp(120.0, 1600.0);
    let h = height.clamp(80.0, 1400.0);
    window
        .set_size(tauri::LogicalSize::new(w, h))
        .map_err(|e| e.to_string())
}

/// Keep the window reachable if the saved position ends up off-screen.
#[tauri::command]
fn reset_position(window: WebviewWindow) -> Result<(), String> {
    window
        .set_position(PhysicalPosition::new(80, 80))
        .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            set_click_through,
            set_always_on_top,
            resize_window,
            reset_position
        ])
        .setup(|app| {
            // ---- tray ----
            let toggle_visible =
                MenuItem::with_id(app, "toggle_visible", "显示 / 隐藏桌宠", true, None::<&str>)?;
            let panel = MenuItem::with_id(app, "toggle_panel", "房间 / 设置面板", true, None::<&str>)?;
            let click_through =
                MenuItem::with_id(app, "toggle_click_through", "切换点击穿透", true, None::<&str>)?;
            let reset = MenuItem::with_id(app, "reset_position", "重置位置", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&toggle_visible, &panel, &click_through, &reset, &quit])?;

            let mut tray = TrayIconBuilder::new()
                .tooltip("AsoulTappo")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
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
                            let _ = w.set_position(PhysicalPosition::new(80, 80));
                            let _ = w.show();
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
