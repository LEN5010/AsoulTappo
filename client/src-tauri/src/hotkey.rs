//! Global shortcuts: the hide key, which hides the pet, the panel and the capture window and shows them again, and
//! the click-through key, which flips click-through. Registered with the system, so they need no input permission
//! and do not go through the hook.
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

/// Whether the panel was on screen when the key hid it, so the next press brings it back too.
static PANEL_WAS_SHOWN: AtomicBool = AtomicBool::new(false);
/// The same for the capture window.
static CAPTURE_WAS_SHOWN: AtomicBool = AtomicBool::new(false);

/// What a shortcut does.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Slot {
    Hide,
    ClickThrough,
}

impl Slot {
    fn parse(name: &str) -> Result<Self, String> {
        match name {
            "hide" => Ok(Self::Hide),
            "click-through" => Ok(Self::ClickThrough),
            _ => Err(format!("unknown hotkey {name}")),
        }
    }
    fn index(self) -> usize {
        match self {
            Self::Hide => 0,
            Self::ClickThrough => 1,
        }
    }
    fn label(self) -> &'static str {
        match self {
            Self::Hide => "hide",
            Self::ClickThrough => "click-through",
        }
    }
}

/// The shortcut registered for each slot, in Slot::index order.
static REGISTERED: Mutex<[Option<Shortcut>; 2]> = Mutex::new([None, None]);

fn toggle(app: &AppHandle) {
    let Some(main) = app.get_webview_window("main") else { return };
    let panel = app.get_webview_window("panel");
    let capture = app.get_webview_window("capture");
    if main.is_visible().unwrap_or(true) {
        applog!("hotkey", "hide");
        let shown = panel.as_ref().is_some_and(|p| p.is_visible().unwrap_or(false));
        PANEL_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(p) = panel.filter(|_| shown) {
            let _ = p.hide();
            let _ = app.emit_to("panel", "panel:visible", false);
        }
        let shown = capture.as_ref().is_some_and(|c| c.is_visible().unwrap_or(false));
        CAPTURE_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(c) = capture.filter(|_| shown) {
            let _ = c.hide();
        }
        let _ = main.hide();
    } else {
        applog!("hotkey", "show");
        let _ = main.show();
        if let Some(p) = panel.filter(|_| PANEL_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            let _ = p.show();
            let _ = app.emit_to("panel", "panel:visible", true);
        }
        if let Some(c) = capture.filter(|_| CAPTURE_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            let _ = c.show();
        }
    }
}

fn press(app: &AppHandle, slot: Slot) {
    match slot {
        Slot::Hide => toggle(app),
        // The desk owns the setting, as when the tray flips it.
        Slot::ClickThrough => {
            applog!("hotkey", "toggle click-through");
            let _ = app.emit_to("main", "tray", "toggle-click-through");
        }
    }
}

/// Replaces the shortcut of [slot] ("hide" or "click-through") with [keys] (`Control+Alt+KeyH`); empty removes it.
/// The error is the system's refusal, usually because another program holds the shortcut, or "taken" when the
/// other slot already uses it. On an error the slot keeps no shortcut.
#[tauri::command]
pub fn set_hotkey(app: AppHandle, slot: String, keys: String) -> Result<(), String> {
    let slot = Slot::parse(&slot)?;
    let shortcuts = app.global_shortcut();
    let mut registered = REGISTERED.lock().map_err(|e| e.to_string())?;
    if let Some(old) = registered[slot.index()].take() {
        let _ = shortcuts.unregister(old);
    }
    if keys.is_empty() {
        applog!("hotkey", "{} none", slot.label());
        return Ok(());
    }
    let shortcut: Shortcut = keys.parse().map_err(|e| format!("{e}"))?;
    if registered.iter().flatten().any(|s| *s == shortcut) {
        applog!("hotkey", "{} not registered: taken", slot.label());
        return Err("taken".into());
    }
    let result = shortcuts.on_shortcut(shortcut, move |app, _shortcut, event| {
        if event.state == ShortcutState::Pressed {
            press(app, slot);
        }
    });
    match &result {
        Ok(()) => {
            registered[slot.index()] = Some(shortcut);
            applog!("hotkey", "{} registered", slot.label());
        }
        Err(e) => applog!("hotkey", "{} not registered: {e}", slot.label()),
    }
    result.map_err(|e| e.to_string())
}
