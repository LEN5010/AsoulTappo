//! Running as administrator (Windows).
//!
//! A low-level hook (and Raw Input too) never sees input meant for a window of a higher
//! integrity level: a game run as administrator gets keys and clicks the pet cannot count.
//! The only way around it is for the pet to run elevated as well. That is opt-in: a flag
//! file makes every start ask UAC, and the page offers it when an elevated window is in
//! front. Accounts that cannot elevate themselves (standard users) are never asked, since
//! another account's credentials would run the pet as that account, with its own data.
//!
//! The single-instance check lives here too: it has to run after waiting for an instance that
//! restarted this one, and before the UAC prompt.

use std::path::PathBuf;
use std::time::Duration;

/// Where the "start as administrator" choice is kept. It is read before Tauri starts, so it
/// lives in a plain file under the app config dir (`%APPDATA%\<identifier>`), not in the page.
fn flag_path() -> Option<PathBuf> {
    // Same folder as `app_config_dir()`; must match `identifier` in tauri.conf.json.
    const IDENTIFIER: &str = "io.github.len5010.asoultappo";
    std::env::var_os("APPDATA").map(|dir| PathBuf::from(dir).join(IDENTIFIER).join("run-as-admin"))
}

/// Whether the player chose to start as administrator.
pub fn run_as_admin() -> bool {
    flag_path().and_then(|p| std::fs::read_to_string(p).ok()).is_some_and(|s| s.trim() == "1")
}

pub fn set_run_as_admin(on: bool) -> std::io::Result<()> {
    let Some(path) = flag_path() else {
        return Err(std::io::Error::new(std::io::ErrorKind::NotFound, "no APPDATA"));
    };
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(path, if on { "1" } else { "0" })
}

/// What happened at startup, for the log once it is open.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub enum Startup {
    /// Nothing to do: not chosen, already elevated, or not Windows.
    Normal,
    /// Chosen, but this account cannot elevate itself.
    CannotElevate,
    /// Chosen, and the player declined (or UAC failed): running without it.
    Declined(String),
}

/// What the single-instance check found, for the log once it is open. A second start never
/// gets this far: it exits before opening anything.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub enum Instance {
    /// No other instance was running, or not Windows.
    Only,
    /// Another instance was still running and exited within the grace period (a restart);
    /// how long this one waited for it.
    AfterWait(Duration),
    /// The check itself failed; running without it.
    Unchecked(String),
}

#[cfg(target_os = "windows")]
pub use imp::{blocked, can_elevate, is_elevated, restart_elevated, spawn_watch, startup};

#[cfg(not(target_os = "windows"))]
pub use stub::{can_elevate, is_elevated, restart_elevated, spawn_watch, startup};

#[cfg(target_os = "windows")]
mod imp {
    use std::collections::HashSet;
    use std::ffi::c_void;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::time::{Duration, Instant};

    use serde::Serialize;
    use tauri::Emitter;
    use windows_sys::Win32::Foundation::{
        CloseHandle, GetLastError, HANDLE, ERROR_ACCESS_DENIED, ERROR_ALREADY_EXISTS, ERROR_CANCELLED,
    };
    use windows_sys::Win32::Security::{
        GetTokenInformation, TokenElevationType, TokenElevationTypeLimited, TOKEN_ELEVATION_TYPE, TOKEN_QUERY,
    };
    use windows_sys::Win32::System::Threading::{
        CreateMutexW, GetCurrentProcess, GetCurrentProcessId, OpenProcess, OpenProcessToken, WaitForSingleObject,
        PROCESS_SYNCHRONIZE,
    };
    use windows_sys::Win32::UI::Shell::{ShellExecuteExW, SEE_MASK_NOASYNC, SHELLEXECUTEINFOW};
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    use super::{Instance, Startup};

    /// How long a new elevated instance waits for the one that started it to exit.
    const WAIT_FOR_OLD: u32 = 10_000;
    /// Held by the running instance. `Local\` is the session's namespace, which elevated and
    /// normal processes of the same session share; other sessions (other users) have their own.
    const INSTANCE_MUTEX: &str = "Local\\io.github.len5010.asoultappo.instance";
    /// How long a new start keeps trying while another instance holds the mutex: `relaunch`
    /// starts the new process before the old one has exited.
    const CLAIM_WAIT: Duration = Duration::from_secs(3);
    const CLAIM_EVERY: Duration = Duration::from_millis(100);
    const WATCH_EVERY: Duration = Duration::from_secs(1);
    /// How long an elevated window stays in front before the page offers to restart elevated.
    const TELL_AFTER: Duration = Duration::from_secs(10);

    static BLOCKED: AtomicBool = AtomicBool::new(false);

    pub fn is_elevated() -> bool {
        crate::diag::elevated() == Some(true)
    }

    /// An administrator running with UAC's filtered token: UAC can raise this same account.
    pub fn can_elevate() -> bool {
        unsafe {
            let mut token: HANDLE = std::ptr::null_mut();
            if OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) == 0 {
                return false;
            }
            let mut kind: TOKEN_ELEVATION_TYPE = 0;
            let mut len = 0u32;
            let ok = GetTokenInformation(
                token,
                TokenElevationType,
                &mut kind as *mut TOKEN_ELEVATION_TYPE as *mut c_void,
                std::mem::size_of::<TOKEN_ELEVATION_TYPE>() as u32,
                &mut len,
            );
            CloseHandle(token);
            ok != 0 && kind == TokenElevationTypeLimited
        }
    }

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// Start this program again through UAC. The new instance waits for this one to exit
    /// before it opens its windows, so the two never share the webview's data folder.
    pub fn restart_elevated() -> Result<(), String> {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let file = wide(&exe.to_string_lossy());
        let verb = wide("runas");
        let params = wide(&format!("--wait-for {}", unsafe { GetCurrentProcessId() }));
        unsafe {
            let mut info: SHELLEXECUTEINFOW = std::mem::zeroed();
            info.cbSize = std::mem::size_of::<SHELLEXECUTEINFOW>() as u32;
            info.fMask = SEE_MASK_NOASYNC;
            info.lpVerb = verb.as_ptr();
            info.lpFile = file.as_ptr();
            info.lpParameters = params.as_ptr();
            info.nShow = SW_SHOWNORMAL;
            if ShellExecuteExW(&mut info) != 0 {
                Ok(())
            } else {
                match GetLastError() {
                    ERROR_CANCELLED => Err("cancelled".into()),
                    e => Err(format!("error {e}")),
                }
            }
        }
    }

    /// Before Tauri starts: wait for the instance that restarted this one, exit when another
    /// instance is running, then restart elevated when the player chose it. Exits the process
    /// when the elevated one started.
    pub fn startup() -> (Instance, Startup) {
        let args: Vec<String> = std::env::args().collect();
        if let Some(pid) = args.windows(2).find(|w| w[0] == "--wait-for").and_then(|w| w[1].parse::<u32>().ok()) {
            unsafe {
                let old = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
                if !old.is_null() {
                    WaitForSingleObject(old, WAIT_FOR_OLD);
                    CloseHandle(old);
                }
            }
        }
        // After the wait, so an elevated restart takes over from the instance it replaces; before
        // the UAC decision, so a second start never asks for it.
        let instance = claim_instance();
        if !super::run_as_admin() || is_elevated() {
            return (instance, Startup::Normal);
        }
        if !can_elevate() {
            return (instance, Startup::CannotElevate);
        }
        match restart_elevated() {
            Ok(()) => std::process::exit(0),
            Err(e) => (instance, Startup::Declined(e)),
        }
    }

    /// Take the instance mutex, or exit when another instance still holds it after `CLAIM_WAIT`.
    fn claim_instance() -> Instance {
        let name = wide(INSTANCE_MUTEX);
        let started = Instant::now();
        let mut first = true;
        loop {
            let (mutex, error) = unsafe {
                let mutex = CreateMutexW(std::ptr::null(), 0, name.as_ptr());
                (mutex, GetLastError())
            };
            match (mutex.is_null(), error) {
                // Running already. A normal process cannot open the mutex of an elevated instance at all.
                (false, ERROR_ALREADY_EXISTS) | (true, ERROR_ACCESS_DENIED) => {}
                (true, e) => return Instance::Unchecked(format!("error {e}")),
                // The handle is never closed: it keeps the mutex for as long as this process runs.
                (false, _) if first => return Instance::Only,
                (false, _) => return Instance::AfterWait(started.elapsed()),
            }
            // An open handle keeps the mutex alive after the other instance exits.
            if !mutex.is_null() {
                unsafe { CloseHandle(mutex) };
            }
            if started.elapsed() >= CLAIM_WAIT {
                std::process::exit(0);
            }
            first = false;
            std::thread::sleep(CLAIM_EVERY);
        }
    }

    /// The foreground process outranks this one: it runs elevated and this does not.
    /// Its file name, or `None` when input to the foreground reaches the hook.
    fn foreground_outranks_us() -> Option<String> {
        if is_elevated() {
            return None;
        }
        let (name, elevated) = crate::diag::foreground_process()?;
        elevated.then_some(name)
    }

    /// Whether input is going to a window the hook cannot hear; the watchdog leaves the
    /// hook alone meanwhile, since replacing it would not help.
    pub fn blocked() -> bool {
        BLOCKED.load(Ordering::Relaxed)
    }

    #[derive(Clone, Serialize)]
    #[serde(rename_all = "camelCase")]
    struct Blocked {
        /// The elevated foreground program, or null once input reaches the pet again.
        by: Option<String>,
        can_elevate: bool,
    }

    /// Tell the desk page when an elevated window has stayed in front for `TELL_AFTER` (a game,
    /// not a glance at Task Manager), and again when input reaches the pet once more.
    pub fn spawn_watch(app: tauri::AppHandle) {
        std::thread::spawn(move || {
            let can = can_elevate();
            let mut current: Option<String> = None;
            let mut since = Instant::now();
            let mut told = false;
            let mut logged: HashSet<String> = HashSet::new();
            loop {
                std::thread::sleep(WATCH_EVERY);
                let now = foreground_outranks_us();
                BLOCKED.store(now.is_some(), Ordering::Relaxed);
                if now != current {
                    if told && now.is_none() {
                        let _ = app.emit_to("main", "input-blocked", Blocked { by: None, can_elevate: can });
                        told = false;
                    }
                    current = now;
                    since = Instant::now();
                    continue;
                }
                let Some(name) = &current else { continue };
                if told || since.elapsed() < TELL_AFTER {
                    continue;
                }
                told = true;
                if logged.insert(name.clone()) {
                    applog!(
                        "input",
                        "{name} runs as administrator and AsoulTappo does not: its keys and clicks cannot be counted{}",
                        if can { "" } else { "; this account cannot run AsoulTappo as administrator" }
                    );
                }
                let _ = app.emit_to("main", "input-blocked", Blocked { by: Some(name.clone()), can_elevate: can });
            }
        });
    }
}

#[cfg(not(target_os = "windows"))]
mod stub {
    use super::{Instance, Startup};

    pub fn is_elevated() -> bool {
        false
    }
    pub fn can_elevate() -> bool {
        false
    }
    pub fn restart_elevated() -> Result<(), String> {
        Err("unsupported".into())
    }
    /// Finder and the desktop start a running app only once, so there is no instance check here.
    pub fn startup() -> (Instance, Startup) {
        (Instance::Only, Startup::Normal)
    }
    pub fn spawn_watch(_app: tauri::AppHandle) {}
}
