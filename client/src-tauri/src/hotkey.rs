//! Global shortcuts: the hide key hides the pet, panel, todos, race, dou dizhu and capture windows and restores them,
//! the click-through key, which flips click-through, the monitor key, which moves the pet to the next monitor as the
//! tray does, and the emote keys, which play a quick emote each. Registered with the system, so they need no input
//! permission and do not go through the hook.
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

/// Whether the panel was on screen when the key hid it, so the next press brings it back too.
static PANEL_WAS_SHOWN: AtomicBool = AtomicBool::new(false);
/// The same for the capture window.
static CAPTURE_WAS_SHOWN: AtomicBool = AtomicBool::new(false);
/// The same for the todos' window.
static TODO_WAS_SHOWN: AtomicBool = AtomicBool::new(false);
/// The same for the race window.
static RACE_WAS_SHOWN: AtomicBool = AtomicBool::new(false);
/// The same for the dou dizhu table's window.
static DDZ_WAS_SHOWN: AtomicBool = AtomicBool::new(false);

/// What a shortcut does.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Slot {
    Hide,
    ClickThrough,
    NextMonitor,
    /// The quick emote at this place, from 1.
    Emote(u8),
}

/// How many quick emotes have a key of their own.
const EMOTES: u8 = 8;
const SLOTS: usize = 3 + EMOTES as usize;

impl Slot {
    fn parse(name: &str) -> Result<Self, String> {
        match name {
            "hide" => Ok(Self::Hide),
            "click-through" => Ok(Self::ClickThrough),
            "next-monitor" => Ok(Self::NextMonitor),
            _ => match name.strip_prefix("emote-").and_then(|n| n.parse::<u8>().ok()) {
                Some(n) if (1..=EMOTES).contains(&n) => Ok(Self::Emote(n)),
                _ => Err(format!("unknown hotkey {name}")),
            },
        }
    }
    fn index(self) -> usize {
        match self {
            Self::Hide => 0,
            Self::ClickThrough => 1,
            Self::NextMonitor => 2,
            Self::Emote(n) => 2 + n as usize,
        }
    }
    fn label(self) -> String {
        match self {
            Self::Hide => "hide".into(),
            Self::ClickThrough => "click-through".into(),
            Self::NextMonitor => "next-monitor".into(),
            Self::Emote(n) => format!("emote-{n}"),
        }
    }
}

/// The shortcut registered for each slot, in Slot::index order.
static REGISTERED: Mutex<[Option<Shortcut>; SLOTS]> = Mutex::new([None; SLOTS]);

fn toggle(app: &AppHandle) {
    let Some(main) = app.get_webview_window("main") else { return };
    let panel = app.get_webview_window("panel");
    let capture = app.get_webview_window("capture");
    let todo = app.get_webview_window("todo");
    let race = app.get_webview_window("race");
    let ddz = app.get_webview_window("ddz");
    if main.is_visible().unwrap_or(true) {
        applog!("hotkey", "hide");
        let shown = panel.as_ref().is_some_and(|p| p.is_visible().unwrap_or(false));
        PANEL_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(p) = panel.filter(|_| shown) {
            if p.hide().is_ok() {
                crate::panel_hidden();
            }
            let _ = app.emit_to("panel", "panel:visible", false);
        }
        let shown = capture.as_ref().is_some_and(|c| c.is_visible().unwrap_or(false));
        CAPTURE_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(c) = capture.filter(|_| shown) {
            if c.hide().is_ok() {
                crate::CAPTURE_OPEN.store(false, Ordering::Relaxed);
            }
        }
        let shown = todo.as_ref().is_some_and(|t| t.is_visible().unwrap_or(false));
        TODO_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(t) = todo.filter(|_| shown) {
            let _ = t.hide();
        }
        let shown = race.as_ref().is_some_and(|r| r.is_visible().unwrap_or(false));
        RACE_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(r) = race.filter(|_| shown) {
            let _ = r.hide();
        }
        let shown = ddz.as_ref().is_some_and(|d| d.is_visible().unwrap_or(false));
        DDZ_WAS_SHOWN.store(shown, Ordering::Relaxed);
        if let Some(d) = ddz.filter(|_| shown) {
            if d.hide().is_ok() {
                crate::DDZ_OPEN.store(false, Ordering::Relaxed);
            }
        }
        // The hit test reads the pet window's visibility from the overlay state, as after the tray's hide.
        let overlay = app.try_state::<Arc<crate::Overlay>>();
        if main.hide().is_ok() {
            if let Some(o) = &overlay {
                o.visible.store(false, Ordering::Relaxed);
            }
        }
        crate::BOSS_HIDDEN.store(true, Ordering::Relaxed);
    } else {
        applog!("hotkey", "show");
        crate::BOSS_HIDDEN.store(false, Ordering::Relaxed);
        if main.show().is_ok() {
            if let Some(o) = app.try_state::<Arc<crate::Overlay>>() {
                o.visible.store(true, Ordering::Relaxed);
            }
        }
        #[cfg(target_os = "windows")]
        crate::transparency::request("shown by the hide hotkey");
        let panel = panel.filter(|_| PANEL_WAS_SHOWN.swap(false, Ordering::Relaxed));
        if let Some(p) = &panel {
            if p.show().is_ok() {
                crate::PANEL_VISIBLE.store(true, Ordering::Relaxed);
            }
            let _ = app.emit_to("panel", "panel:visible", true);
        }
        if let Some(c) = capture.filter(|_| CAPTURE_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            if c.show().is_ok() {
                crate::CAPTURE_OPEN.store(true, Ordering::Relaxed);
            }
        }
        if let Some(t) = todo.filter(|_| TODO_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            let _ = t.show();
        }
        if let Some(r) = race.filter(|_| RACE_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            let _ = r.show();
        }
        if let Some(d) = ddz.filter(|_| DDZ_WAS_SHOWN.swap(false, Ordering::Relaxed)) {
            if d.show().is_ok() {
                crate::DDZ_OPEN.store(true, Ordering::Relaxed);
            }
        }
        // The panel is a regular window: shown alone it stays where it was, under the window in front. The key press
        // lets this process take the foreground, so the panel comes to the front as when it is opened by hand.
        if let Some(p) = panel {
            let _ = p.set_focus();
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
        // Run on the main thread, as the tray's entry is: the shortcut's callback may come on another one.
        Slot::NextMonitor => {
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || {
                let overlay = handle.state::<Arc<crate::Overlay>>();
                crate::move_to_next_monitor(&handle, &overlay, "hotkey", true);
            });
        }
        // The desk knows which emotes its strip holds.
        Slot::Emote(n) => {
            let _ = app.emit_to("main", "emote-key", n);
        }
    }
}

/// Replaces the shortcut of [slot] ("hide", "click-through", "next-monitor", "emote-1" to "emote-8") with [keys]
/// (`Control+Alt+KeyH`); empty removes it. The error is the system's refusal, usually because another program holds the shortcut, or
/// "taken" when another slot already uses it. On an error the slot keeps no shortcut.
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
