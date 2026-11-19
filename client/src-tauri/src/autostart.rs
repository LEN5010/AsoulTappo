//! Start at login. The system's own record is the only state: the switch on the settings page reads it back every
//! time, so turning the pet off in System Settings or in Task Manager shows there as well.
//!
//! - macOS 13 and later: `SMAppService.mainAppService`, listed under Open at Login in System Settings.
//! - macOS 10.15 to 12: a LaunchAgent plist in `~/Library/LaunchAgents`.
//! - Windows: the value named after `productName` (src/edition.rs) under HKCU `...\CurrentVersion\Run`, the value
//!   the NSIS uninstaller removes (outside an update). A start turned off in Task Manager is kept under `StartupApproved\Run`; turning it on here
//!   deletes that record.
//!
//! A macOS copy started from a disk image or from a quarantined download runs from a path that is gone at the next
//! login (`/Volumes/...`, App Translocation), so it cannot be registered until it is moved to Applications.

#[derive(serde::Serialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    pub supported: bool,
    pub enabled: bool,
    /// macOS: runs from a path that does not last; move the app to Applications first.
    pub needs_move: bool,
}

/// A path the app will not be found at after a restart.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn transient(exe: &str) -> bool {
    exe.starts_with("/Volumes/") || exe.contains("/AppTranslocation/")
}

#[cfg(target_os = "macos")]
mod imp {
    use super::{transient, Status};
    use objc2::rc::Retained;
    use objc2::runtime::{AnyClass, AnyObject};
    use objc2::msg_send;
    use objc2_foundation::NSError;
    use std::path::PathBuf;

    // SMAppService ships in ServiceManagement from macOS 13; on older systems the framework is there without the
    // class, so the class is looked up at run time.
    #[link(name = "ServiceManagement", kind = "framework")]
    extern "C" {}

    /// SMAppServiceStatus.
    const ENABLED: isize = 1;
    const REQUIRES_APPROVAL: isize = 2;

    /// The LaunchAgent of macOS 10.15 to 12, one per edition.
    const LABEL: &str = crate::edition::IDENTIFIER;

    fn class() -> Option<&'static AnyClass> {
        AnyClass::get(c"SMAppService")
    }

    fn main_app(class: &AnyClass) -> Option<Retained<AnyObject>> {
        // SAFETY: `+mainAppService` takes nothing and returns the service of the running app.
        unsafe { msg_send![class, mainAppService] }
    }

    fn service_status(service: &AnyObject) -> isize {
        // SAFETY: `-status` returns an NSInteger.
        unsafe { msg_send![service, status] }
    }

    fn exe() -> Option<String> {
        std::env::current_exe().ok().map(|p| p.display().to_string())
    }

    fn agent_path() -> Option<PathBuf> {
        std::env::var_os("HOME").map(|home| PathBuf::from(home).join("Library/LaunchAgents").join(format!("{LABEL}.plist")))
    }

    fn escape(s: &str) -> String {
        s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
    }

    pub(super) fn agent_plist(exe: &str) -> String {
        format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>AssociatedBundleIdentifiers</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
"#,
            escape(exe)
        )
    }

    pub fn status() -> Status {
        let needs_move = exe().is_none_or(|e| transient(&e));
        let enabled = match class() {
            Some(class) => main_app(class).is_some_and(|s| service_status(&s) == ENABLED),
            None => agent_path().is_some_and(|p| p.exists()),
        };
        Status { supported: true, enabled, needs_move }
    }

    pub fn set(enabled: bool) -> Result<(), String> {
        if enabled && status().needs_move {
            return Err("move".into());
        }
        let Some(class) = class() else {
            let path = agent_path().ok_or("no home folder")?;
            if !enabled {
                return match std::fs::remove_file(&path) {
                    Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(e.to_string()),
                    _ => Ok(()),
                };
            }
            let exe = exe().ok_or("no executable path")?;
            if let Some(dir) = path.parent() {
                std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
            }
            return std::fs::write(&path, agent_plist(&exe)).map_err(|e| e.to_string());
        };
        let service = main_app(class).ok_or("no main app service")?;
        let result: Result<(), Retained<NSError>> = if enabled {
            // SAFETY: `-registerAndReturnError:` returns NO and sets the error on failure.
            unsafe { msg_send![&*service, registerAndReturnError: _] }
        } else {
            // SAFETY: as above.
            unsafe { msg_send![&*service, unregisterAndReturnError: _] }
        };
        // Turned off by the player in System Settings: registering again cannot override that, only the switch
        // there can, so that page is opened.
        if enabled && service_status(&service) == REQUIRES_APPROVAL {
            // SAFETY: a class method that takes nothing.
            let _: () = unsafe { msg_send![class, openSystemSettingsLoginItems] };
            return Err("approval".into());
        }
        result.map_err(|e| format!("error {}", e.code()))
    }

    /// Nothing to bring up to date: the service follows the bundle, and the plist names the one path an installed
    /// copy lives at.
    pub fn refresh() {}
}

#[cfg(target_os = "windows")]
mod imp {
    use super::Status;
    use std::ffi::c_void;
    use std::ptr::null_mut;
    use windows_sys::Win32::Foundation::{ERROR_FILE_NOT_FOUND, ERROR_SUCCESS};
    use windows_sys::Win32::System::Registry::{
        RegDeleteKeyValueW, RegGetValueW, RegSetKeyValueW, HKEY_CURRENT_USER, REG_SZ, RRF_RT_REG_BINARY, RRF_RT_REG_SZ,
    };

    const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
    const APPROVED: &str = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run";
    /// `${PRODUCTNAME}`, the value Tauri's uninstaller deletes: each edition's uninstaller removes only its own.
    const NAME: &str = crate::edition::PRODUCT_NAME;

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn command() -> Option<String> {
        std::env::current_exe().ok().map(|p| format!("\"{}\"", p.display()))
    }

    fn read_run() -> Option<String> {
        let (key, name) = (wide(RUN), wide(NAME));
        let mut len = 0u32;
        // SAFETY: a size query with no buffer.
        let ok = unsafe {
            RegGetValueW(HKEY_CURRENT_USER, key.as_ptr(), name.as_ptr(), RRF_RT_REG_SZ, null_mut(), null_mut(), &mut len)
        };
        if ok != ERROR_SUCCESS || len == 0 {
            return None;
        }
        let mut buf = vec![0u16; (len as usize).div_ceil(2)];
        // SAFETY: `buf` holds `len` bytes.
        let ok = unsafe {
            RegGetValueW(
                HKEY_CURRENT_USER,
                key.as_ptr(),
                name.as_ptr(),
                RRF_RT_REG_SZ,
                null_mut(),
                buf.as_mut_ptr() as *mut c_void,
                &mut len,
            )
        };
        if ok != ERROR_SUCCESS {
            return None;
        }
        let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
        Some(String::from_utf16_lossy(&buf[..end]))
    }

    /// Task Manager keeps 12 bytes per entry; an odd first byte is turned off.
    fn approved() -> bool {
        let (key, name) = (wide(APPROVED), wide(NAME));
        let mut data = [0u8; 12];
        let mut len = data.len() as u32;
        // SAFETY: `data` holds `len` bytes.
        let ok = unsafe {
            RegGetValueW(
                HKEY_CURRENT_USER,
                key.as_ptr(),
                name.as_ptr(),
                RRF_RT_REG_BINARY,
                null_mut(),
                data.as_mut_ptr() as *mut c_void,
                &mut len,
            )
        };
        ok != ERROR_SUCCESS || len == 0 || data[0] & 1 == 0
    }

    fn delete(subkey: &str) -> Result<(), String> {
        let (key, name) = (wide(subkey), wide(NAME));
        // SAFETY: both strings are NUL-terminated.
        let ok = unsafe { RegDeleteKeyValueW(HKEY_CURRENT_USER, key.as_ptr(), name.as_ptr()) };
        if ok == ERROR_SUCCESS || ok == ERROR_FILE_NOT_FOUND {
            Ok(())
        } else {
            Err(format!("RegDeleteKeyValueW {ok}"))
        }
    }

    fn write_run(command: &str) -> Result<(), String> {
        let (key, name, data) = (wide(RUN), wide(NAME), wide(command));
        // SAFETY: `data` is a NUL-terminated UTF-16 string, its size in bytes includes the NUL.
        let ok = unsafe {
            RegSetKeyValueW(
                HKEY_CURRENT_USER,
                key.as_ptr(),
                name.as_ptr(),
                REG_SZ,
                data.as_ptr() as *const c_void,
                (data.len() * 2) as u32,
            )
        };
        if ok == ERROR_SUCCESS {
            Ok(())
        } else {
            Err(format!("RegSetKeyValueW {ok}"))
        }
    }

    pub fn status() -> Status {
        Status { supported: true, enabled: read_run().is_some() && approved(), needs_move: false }
    }

    pub fn set(enabled: bool) -> Result<(), String> {
        if !enabled {
            return delete(RUN);
        }
        write_run(&command().ok_or("no executable path")?)?;
        delete(APPROVED)
    }

    /// The entry follows the install folder if the app was installed somewhere else since.
    pub fn refresh() {
        let (Some(saved), Some(now)) = (read_run(), command()) else { return };
        if !saved.eq_ignore_ascii_case(&now) {
            match write_run(&now) {
                Ok(()) => crate::applog!("app", "start at login moved to the current install folder"),
                Err(e) => crate::applog!("app", "start at login update failed: {e}"),
            }
        }
    }
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
mod imp {
    use super::Status;

    pub fn status() -> Status {
        Status { supported: false, enabled: false, needs_move: false }
    }

    pub fn set(_enabled: bool) -> Result<(), String> {
        Err("unsupported".into())
    }

    pub fn refresh() {}
}

pub use imp::{refresh, status};

#[tauri::command]
pub fn autostart_status() -> Status {
    status()
}

/// Turns start at login on or off and answers the state read back from the system. Rejects with "move" (macOS: the
/// app runs from a disk image or a quarantined download) or "approval" (macOS: turned off in System Settings, which
/// was opened to the switch).
#[tauri::command]
pub fn set_autostart(enabled: bool) -> Result<Status, String> {
    match imp::set(enabled) {
        Ok(()) => {
            crate::applog!("app", "start at login {}", if enabled { "on" } else { "off" });
            Ok(status())
        }
        Err(e) => {
            crate::applog!("app", "start at login {} failed: {e}", if enabled { "on" } else { "off" });
            Err(e)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copies_that_move_away_are_transient() {
        assert!(transient("/Volumes/AsoulTappo/AsoulTappo.app/Contents/MacOS/AsoulTappo"));
        assert!(transient(
            "/private/var/folders/x/T/AppTranslocation/1A2B/d/AsoulTappo.app/Contents/MacOS/AsoulTappo"
        ));
        assert!(!transient("/Applications/AsoulTappo.app/Contents/MacOS/AsoulTappo"));
        assert!(!transient("/Users/me/Applications/AsoulTappo.app/Contents/MacOS/AsoulTappo"));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn the_agent_plist_escapes_the_path() {
        let plist = imp::agent_plist("/Users/a&b/AsoulTappo.app/Contents/MacOS/AsoulTappo");
        assert!(plist.contains("<string>/Users/a&amp;b/AsoulTappo.app/Contents/MacOS/AsoulTappo</string>"));
        assert!(plist.contains("<key>RunAtLoad</key>\n  <true/>"));
    }
}
