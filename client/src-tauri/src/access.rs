//! macOS: whether the global hook may hear other apps' keys and clicks. Either Input Monitoring
//! or Accessibility is enough. Checked with the preflight calls, which never show a system prompt;
//! the main window gets `input-access` (true = missing) whenever the answer changes.

#[cfg(target_os = "macos")]
mod imp {
    use std::time::Duration;
    use tauri::{AppHandle, Emitter};

    /// Input Monitoring in System Settings; the only page `open_input_settings` opens.
    const SETTINGS: &str = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent";
    /// Same pace as the hook's retry, so the hint goes away soon after the hook comes back.
    const POLL: Duration = Duration::from_secs(5);

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGPreflightListenEventAccess() -> bool;
    }
    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        fn AXIsProcessTrusted() -> u8;
    }

    pub fn missing() -> bool {
        // SAFETY: both take no arguments and only read the app's permission state.
        unsafe { !CGPreflightListenEventAccess() && AXIsProcessTrusted() == 0 }
    }

    pub fn spawn_watch(app: AppHandle) {
        std::thread::spawn(move || {
            let mut last = false;
            loop {
                let now = missing();
                if now != last {
                    applog!(
                        "hook",
                        "{}",
                        if now { "no Input Monitoring or Accessibility permission" } else { "input permission granted" }
                    );
                    let _ = app.emit_to("main", "input-access", now);
                    last = now;
                }
                std::thread::sleep(POLL);
            }
        });
    }

    pub fn open_settings() -> Result<(), String> {
        std::process::Command::new("open").arg(SETTINGS).spawn().map(|_| ()).map_err(|e| e.to_string())
    }
}

#[cfg(not(target_os = "macos"))]
mod imp {
    pub fn missing() -> bool {
        false
    }
    pub fn spawn_watch(_app: tauri::AppHandle) {}
    pub fn open_settings() -> Result<(), String> {
        Err("unsupported".into())
    }
}

pub use imp::spawn_watch;

/// Whether the hook lacks the permission it needs; always false outside macOS.
#[tauri::command]
pub fn input_access_missing() -> bool {
    imp::missing()
}

/// Opens the Input Monitoring page of System Settings (macOS only).
#[tauri::command]
pub fn open_input_settings() -> Result<(), String> {
    imp::open_settings()
}
