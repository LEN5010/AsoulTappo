//! The hide key: one global shortcut that hides the pet and the panel, and shows them again.
//! Registered with the system, so it needs no input permission and does not go through the hook.
use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

/// Whether the panel was on screen when the key hid it, so the next press brings it back too.
static PANEL_WAS_SHOWN: AtomicBool = AtomicBool::new(false);

fn toggle(app: &AppHandle) {
    let Some(main) = app.get_webview_window("main") else { return };
    let panel = app.get_webview_window("panel");
    if main.is_visible().unwrap_or(true) {
        applog!("hotkey", "hide");
        let shown = panel.as_ref().is_some_and(|p| p.is_visible().unwrap_or(false));
        PANEL_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(p) = panel.filter(|_| shown) {
            let _ = p.hide();
            let _ = app.emit_to("panel", "panel:visible", false);
        }
        let _ = main.hide();
    } else {
        applog!("hotkey", "show");
        let _ = main.show();
        if let Some(p) = panel.filter(|_| PANEL_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            let _ = p.show();
            let _ = app.emit_to("panel", "panel:visible", true);
        }
    }
}

/// Replaces the hide key with [keys] (`Control+Alt+KeyH`); empty removes it. The error is the system's
/// refusal, usually because another program holds the shortcut.
#[tauri::command]
pub fn set_boss_key(app: AppHandle, keys: String) -> Result<(), String> {
    let shortcuts = app.global_shortcut();
    shortcuts.unregister_all().map_err(|e| e.to_string())?;
    if keys.is_empty() {
        applog!("hotkey", "none");
        return Ok(());
    }
    let shortcut: Shortcut = keys.parse().map_err(|e| format!("{e}"))?;
    let result = shortcuts.on_shortcut(shortcut, |app, _shortcut, event| {
        if event.state == ShortcutState::Pressed {
            toggle(app);
        }
    });
    match &result {
        Ok(()) => applog!("hotkey", "registered"),
        Err(e) => applog!("hotkey", "not registered: {e}"),
    }
    result.map_err(|e| e.to_string())
}
