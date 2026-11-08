//! One-line descriptions of the system for the exportable log (src/applog.rs).
//!
//! Only executable file names, sizes and flags: never window titles or which key was pressed.

/// "Windows 10.0.22631 x86_64" (the real build, not the compatibility version).
pub fn os_version() -> String {
    imp::os_version()
}

/// Whether this process runs elevated (as administrator); None when it cannot be read.
pub fn elevated() -> Option<bool> {
    imp::elevated()
}

/// The foreground window in one line, e.g. `fg=game.exe fullscreen elevated=?`.
/// `fg=self` for our own windows, `fg=none` when nothing is in front. `elevated=?` means the
/// process token could not be opened, which usually means that process is elevated or protected.
pub fn foreground() -> String {
    imp::foreground()
}

#[cfg(target_os = "windows")]
mod imp {
    use std::ffi::c_void;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE, HWND, RECT};
    use windows_sys::Win32::Graphics::Gdi::{GetMonitorInfoW, MonitorFromWindow, MONITORINFO, MONITOR_DEFAULTTONEAREST};
    use windows_sys::Win32::Security::{GetTokenInformation, TokenElevation, TOKEN_ELEVATION, TOKEN_QUERY};
    use windows_sys::Win32::System::LibraryLoader::{GetModuleHandleW, GetProcAddress};
    use windows_sys::Win32::System::SystemInformation::OSVERSIONINFOW;
    use windows_sys::Win32::System::Threading::{
        GetCurrentProcess, GetCurrentProcessId, OpenProcess, OpenProcessToken, QueryFullProcessImageNameW,
        PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowRect, GetWindowThreadProcessId};

    pub fn os_version() -> String {
        // GetVersionExW reports 6.2 to apps without a compatibility manifest; RtlGetVersion does not.
        type RtlGetVersion = unsafe extern "system" fn(*mut OSVERSIONINFOW) -> i32;
        let ntdll: Vec<u16> = "ntdll.dll\0".encode_utf16().collect();
        let version = unsafe {
            let module = GetModuleHandleW(ntdll.as_ptr());
            if module.is_null() {
                None
            } else {
                GetProcAddress(module, c"RtlGetVersion".as_ptr().cast()).and_then(|f| {
                    let f: RtlGetVersion = std::mem::transmute(f);
                    let mut info: OSVERSIONINFOW = std::mem::zeroed();
                    info.dwOSVersionInfoSize = std::mem::size_of::<OSVERSIONINFOW>() as u32;
                    (f(&mut info) == 0).then_some(info)
                })
            }
        };
        match version {
            Some(v) => format!(
                "Windows {}.{}.{} {}",
                v.dwMajorVersion,
                v.dwMinorVersion,
                v.dwBuildNumber,
                std::env::consts::ARCH
            ),
            None => format!("Windows (version unknown) {}", std::env::consts::ARCH),
        }
    }

    pub fn elevated() -> Option<bool> {
        unsafe { token_elevated(GetCurrentProcess()) }
    }

    pub fn foreground() -> String {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.is_null() {
                return "fg=none".into();
            }
            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, &mut pid);
            let mut out = if pid == GetCurrentProcessId() {
                "fg=self".to_string()
            } else {
                let process = if pid == 0 {
                    std::ptr::null_mut()
                } else {
                    OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
                };
                if process.is_null() {
                    format!("fg=pid:{pid} elevated=?")
                } else {
                    let name = exe_name(process).unwrap_or_else(|| "?".into());
                    let elevated = match token_elevated(process) {
                        Some(true) => "yes",
                        Some(false) => "no",
                        None => "?",
                    };
                    CloseHandle(process);
                    format!("fg={name} elevated={elevated}")
                }
            };
            if covers_monitor(hwnd) {
                // "fg=name fullscreen elevated=..."
                let at = out.find(' ').unwrap_or(out.len());
                out.insert_str(at, " fullscreen");
            }
            out
        }
    }

    /// File name of the process image, without its directory.
    unsafe fn exe_name(process: HANDLE) -> Option<String> {
        let mut buf = [0u16; 1024];
        let mut len = buf.len() as u32;
        if unsafe { QueryFullProcessImageNameW(process, PROCESS_NAME_WIN32, buf.as_mut_ptr(), &mut len) } == 0 {
            return None;
        }
        let path = String::from_utf16_lossy(&buf[..len as usize]);
        path.rsplit(['\\', '/']).next().map(str::to_owned)
    }

    unsafe fn token_elevated(process: HANDLE) -> Option<bool> {
        unsafe {
            let mut token: HANDLE = std::ptr::null_mut();
            if OpenProcessToken(process, TOKEN_QUERY, &mut token) == 0 {
                return None;
            }
            let mut elevation = TOKEN_ELEVATION { TokenIsElevated: 0 };
            let mut returned = 0u32;
            let ok = GetTokenInformation(
                token,
                TokenElevation,
                &mut elevation as *mut TOKEN_ELEVATION as *mut c_void,
                std::mem::size_of::<TOKEN_ELEVATION>() as u32,
                &mut returned,
            );
            CloseHandle(token);
            (ok != 0).then_some(elevation.TokenIsElevated != 0)
        }
    }

    /// Whether the window covers its whole monitor (borderless or exclusive fullscreen).
    unsafe fn covers_monitor(hwnd: HWND) -> bool {
        unsafe {
            let mut rect = RECT { left: 0, top: 0, right: 0, bottom: 0 };
            if GetWindowRect(hwnd, &mut rect) == 0 {
                return false;
            }
            let monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
            let mut info: MONITORINFO = std::mem::zeroed();
            info.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
            if monitor.is_null() || GetMonitorInfoW(monitor, &mut info) == 0 {
                return false;
            }
            let m = info.rcMonitor;
            rect.left <= m.left && rect.top <= m.top && rect.right >= m.right && rect.bottom >= m.bottom
        }
    }
}

#[cfg(not(target_os = "windows"))]
mod imp {
    pub fn os_version() -> String {
        format!("{} {}", std::env::consts::OS, std::env::consts::ARCH)
    }

    pub fn elevated() -> Option<bool> {
        None
    }

    pub fn foreground() -> String {
        "fg=n/a".into()
    }
}
