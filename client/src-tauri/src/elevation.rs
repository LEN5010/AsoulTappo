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
//! restarted this one, and before the UAC prompt. A second start asks the running instance to
//! show its panel (a named event) and exits.

use std::path::PathBuf;
use std::time::Duration;

/// Where the "start as administrator" choice is kept. It is read before Tauri starts, so it
/// lives in a plain file under the app config dir (`%APPDATA%\<identifier>`), not in the page.
fn flag_path() -> Option<PathBuf> {
    // Same folder as `app_config_dir()`, which follows `identifier` in the edition's Tauri configuration.
    std::env::var_os("APPDATA").map(|dir| PathBuf::from(dir).join(crate::edition::IDENTIFIER).join("run-as-admin"))
}

/// Held by the running instance. `Local\` is the session's namespace, which elevated and normal processes of the
/// same session share; other sessions (other users) have their own. One per edition, so both can run.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
fn instance_mutex() -> String {
    format!("Local\\{}.instance", crate::edition::IDENTIFIER)
}

/// Set by a second start to bring the running instance's panel up (`win::ask_to_show`). One per edition, like the
/// mutex: a start of one edition does not raise the other's panel.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
fn show_event() -> String {
    format!("Local\\{}.show", crate::edition::IDENTIFIER)
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
pub use imp::{blocked, can_elevate, is_elevated, restart_elevated, spawn_show_listener, spawn_watch, startup};

#[cfg(not(target_os = "windows"))]
pub use stub::{can_elevate, is_elevated, restart_elevated, spawn_show_listener, spawn_watch, startup};

#[cfg(target_os = "windows")]
mod imp {
    use std::collections::HashSet;
    use std::ffi::c_void;
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use std::time::{Duration, Instant};

    use serde::Serialize;
    use tauri::Emitter;
    use windows_sys::Win32::Foundation::{
        CloseHandle, GetLastError, HANDLE, ERROR_ACCESS_DENIED, ERROR_ALREADY_EXISTS, ERROR_CANCELLED, WAIT_OBJECT_0,
    };
    use windows_sys::Win32::Security::{
        AddAccessAllowedAce, AddMandatoryAce, CreateWellKnownSid, GetTokenInformation, InitializeAcl,
        InitializeSecurityDescriptor, SetSecurityDescriptorDacl, SetSecurityDescriptorSacl, TokenElevationType,
        TokenElevationTypeLimited, WinMediumLabelSid, WinWorldSid, ACL_REVISION, SECURITY_ATTRIBUTES,
        SECURITY_DESCRIPTOR, SECURITY_MAX_SID_SIZE, TOKEN_ELEVATION_TYPE, TOKEN_QUERY,
    };
    use windows_sys::Win32::System::Threading::{
        CreateEventExW, CreateMutexW, GetCurrentProcess, GetCurrentProcessId, OpenEventW, OpenProcess, OpenProcessToken,
        SetEvent, WaitForSingleObject, EVENT_MODIFY_STATE, INFINITE, PROCESS_SYNCHRONIZE, SYNCHRONIZATION_SYNCHRONIZE,
    };
    use windows_sys::Win32::UI::Shell::{ShellExecuteExW, SEE_MASK_NOASYNC, SHELLEXECUTEINFOW};
    use windows_sys::Win32::UI::WindowsAndMessaging::{AllowSetForegroundWindow, ASFW_ANY, SW_SHOWNORMAL};

    use super::{Instance, Startup};

    /// How long a new elevated instance waits for the one that started it to exit.
    const WAIT_FOR_OLD: u32 = 10_000;
    /// How long a new start keeps trying while another instance holds the mutex: `relaunch`
    /// starts the new process before the old one has exited.
    const CLAIM_WAIT: Duration = Duration::from_secs(3);
    const CLAIM_EVERY: Duration = Duration::from_millis(100);
    /// How long a second start waits before asking the running instance to show its panel: a restart through
    /// `relaunch` starts the new process a moment before the old one exits, and that old one should not be asked.
    const ASK_AFTER: Duration = Duration::from_millis(500);
    /// `SYSTEM_MANDATORY_LABEL_NO_WRITE_UP` and `SECURITY_DESCRIPTOR_REVISION` (Win32_System_SystemServices).
    const NO_WRITE_UP: u32 = 1;
    const DESCRIPTOR_REVISION: u32 = 1;
    const WATCH_EVERY: Duration = Duration::from_secs(1);
    /// How long an elevated window stays in front before the page offers to restart elevated.
    const TELL_AFTER: Duration = Duration::from_secs(10);

    static BLOCKED: AtomicBool = AtomicBool::new(false);
    /// The show event's handle (`show_event`), 0 when this instance has none.
    static SHOW: AtomicUsize = AtomicUsize::new(0);
    /// A thread waits on `SHOW` already (`spawn_show_listener`).
    static LISTENING: AtomicBool = AtomicBool::new(false);

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
        // Started by `restart_elevated` to replace the running instance, or at login: either way not by the player,
        // so a running instance is not asked to raise its panel.
        let quiet = args.iter().any(|a| a == "--wait-for" || a == crate::autostart::WINDOWS_ARG);
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
        let instance = claim_instance(quiet);
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

    /// Take the instance mutex, or exit when another instance still holds it after `CLAIM_WAIT`. Meanwhile a start
    /// by the player (not `quiet`) asks the running instance to show its panel; it keeps waiting after that, so an
    /// instance that was on its way out is still replaced.
    fn claim_instance(quiet: bool) -> Instance {
        let name = wide(&super::instance_mutex());
        let started = Instant::now();
        let mut first = true;
        let mut asked = false;
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
                (false, _) => {
                    create_show_event();
                    return if first { Instance::Only } else { Instance::AfterWait(started.elapsed()) };
                }
            }
            // An open handle keeps the mutex alive after the other instance exits.
            if !mutex.is_null() {
                unsafe { CloseHandle(mutex) };
            }
            // Until it works: the running instance creates the event a moment after it takes the mutex.
            if !quiet && !asked && started.elapsed() >= ASK_AFTER {
                asked = ask_to_show();
            }
            if started.elapsed() >= CLAIM_WAIT {
                std::process::exit(0);
            }
            first = false;
            std::thread::sleep(CLAIM_EVERY);
        }
    }

    /// The running instance's side of the show event (`show_event`), auto-reset. Its handle is never closed, like the mutex's. It asks only for
    /// SYNCHRONIZE, all the wait needs: when the event outlives the instance this one replaces (a second start still
    /// holds it), this opens it, and the DACL above would refuse full access.
    fn create_show_event() {
        let name = wide(&super::show_event());
        let event =
            signalable_by_session(|sa| unsafe { CreateEventExW(sa, name.as_ptr(), 0, SYNCHRONIZATION_SYNCHRONIZE) });
        if !event.is_null() {
            SHOW.store(event as usize, Ordering::Relaxed);
        }
    }

    /// Set the running instance's show event. This start came from the player, so it may pass the foreground on:
    /// the panel then comes to the front instead of flashing in the taskbar.
    fn ask_to_show() -> bool {
        let name = wide(&super::show_event());
        unsafe {
            let event = OpenEventW(EVENT_MODIFY_STATE, 0, name.as_ptr());
            if event.is_null() {
                return false;
            }
            AllowSetForegroundWindow(ASFW_ANY);
            let ok = SetEvent(event) != 0;
            CloseHandle(event);
            ok
        }
    }

    /// Calls `create` with security attributes that let any process of the session set the object, an elevated
    /// instance's included: a medium integrity label (a normal process cannot write to an elevated one's objects
    /// otherwise) and a DACL that grants everyone only SYNCHRONIZE and EVENT_MODIFY_STATE. The creator's handle
    /// has full access regardless. Falls back to the default security when either step fails.
    fn signalable_by_session(create: impl Fn(*const SECURITY_ATTRIBUTES) -> HANDLE) -> HANDLE {
        unsafe {
            // SIDs and ACLs are DWORD aligned.
            let mut world = [0u32; SECURITY_MAX_SID_SIZE as usize / 4];
            let mut medium = [0u32; SECURITY_MAX_SID_SIZE as usize / 4];
            let mut world_len = SECURITY_MAX_SID_SIZE;
            let mut medium_len = SECURITY_MAX_SID_SIZE;
            let mut dacl = [0u32; 32];
            let mut sacl = [0u32; 32];
            let acl_len = std::mem::size_of_val(&dacl) as u32;
            let mut sd: SECURITY_DESCRIPTOR = std::mem::zeroed();
            let sd_ptr = &mut sd as *mut SECURITY_DESCRIPTOR as *mut c_void;
            let built = CreateWellKnownSid(WinWorldSid, std::ptr::null_mut(), world.as_mut_ptr().cast(), &mut world_len) != 0
                && CreateWellKnownSid(WinMediumLabelSid, std::ptr::null_mut(), medium.as_mut_ptr().cast(), &mut medium_len)
                    != 0
                && InitializeAcl(dacl.as_mut_ptr().cast(), acl_len, ACL_REVISION) != 0
                && AddAccessAllowedAce(
                    dacl.as_mut_ptr().cast(),
                    ACL_REVISION,
                    SYNCHRONIZATION_SYNCHRONIZE | EVENT_MODIFY_STATE,
                    world.as_mut_ptr().cast(),
                ) != 0
                && InitializeAcl(sacl.as_mut_ptr().cast(), acl_len, ACL_REVISION) != 0
                && AddMandatoryAce(sacl.as_mut_ptr().cast(), ACL_REVISION, 0, NO_WRITE_UP, medium.as_mut_ptr().cast()) != 0
                && InitializeSecurityDescriptor(sd_ptr, DESCRIPTOR_REVISION) != 0
                && SetSecurityDescriptorDacl(sd_ptr, 1, dacl.as_ptr().cast(), 0) != 0
                && SetSecurityDescriptorSacl(sd_ptr, 1, sacl.as_ptr().cast(), 0) != 0;
            if built {
                let sa = SECURITY_ATTRIBUTES {
                    nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
                    lpSecurityDescriptor: sd_ptr,
                    bInheritHandle: 0,
                };
                let handle = create(&sa);
                if !handle.is_null() {
                    return handle;
                }
            }
        }
        create(std::ptr::null())
    }

    /// Wait for a second start's show event and raise the panel the way the tray does. Started by the desk page once
    /// it listens to the tray (`watch_second_start`), so no request is sent before anyone hears it: one set earlier
    /// stays in the event until the wait begins. Only once per run; a reload of the page does not start another.
    pub fn spawn_show_listener(app: tauri::AppHandle) {
        let event = SHOW.load(Ordering::Relaxed);
        if event == 0 || LISTENING.swap(true, Ordering::Relaxed) {
            return;
        }
        std::thread::spawn(move || loop {
            let waited = unsafe { WaitForSingleObject(event as HANDLE, INFINITE) };
            if waited != WAIT_OBJECT_0 {
                applog!("app", "waiting for a second start failed ({waited}, error {})", unsafe { GetLastError() });
                return;
            }
            applog!("app", "started again: raise panel");
            let _ = app.emit_to("main", "tray", "raise-panel");
        });
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
    /// macOS sends a second open of the app to the running one as a reopen event (lib.rs, `RunEvent::Reopen`).
    pub fn spawn_show_listener(_app: tauri::AppHandle) {}
}

#[cfg(test)]
mod tests {
    /// The online edition's mutex is the one installed copies hold: a new name would let an old and a new
    /// instance run at once during an update.
    #[cfg(not(feature = "standalone"))]
    #[test]
    fn online_instance_mutex_stays_as_installed() {
        assert_eq!(super::instance_mutex(), "Local\\io.github.len5010.asoultappo.instance");
        assert_eq!(super::show_event(), "Local\\io.github.len5010.asoultappo.show");
    }
}
