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

/// The foreground program's file name and whether it surely runs elevated (Windows).
#[cfg(target_os = "windows")]
pub fn foreground_process() -> Option<(String, bool)> {
    imp::foreground_process()
}

/// Remember the pet window, so the lines below can tell it apart from the panel.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub fn set_overlay(hwnd: isize) {
    imp::set_overlay(hwnd)
}

/// Whether the pet window lets the mouse through right now, read from its window style
/// (WS_EX_TRANSPARENT) rather than from what the hit test last asked for.
pub fn overlay_passes() -> Option<bool> {
    imp::overlay_passes()
}

/// `foreground()` plus the window class, whether it is topmost, its rectangle, and whether
/// the pet window is above or below it.
pub fn foreground_detail() -> String {
    imp::foreground_detail()
}

/// Cursor position (physical px) and which window is under it: `pet window`, `panel`,
/// another program's file name, or `none`.
pub fn under_cursor() -> String {
    imp::under_cursor()
}

/// Debug build: log the foreground window whenever it, or the pet window's place above or
/// below it, changes.
pub fn spawn_foreground_watch() {
    if crate::applog::DEBUG {
        std::thread::spawn(|| {
            let mut last = String::new();
            loop {
                std::thread::sleep(std::time::Duration::from_millis(500));
                let key = imp::foreground_key();
                if key != last {
                    last = key;
                    debuglog!("fg", "{}", foreground_detail());
                }
            }
        });
    }
}

#[cfg(target_os = "windows")]
mod imp {
    use std::ffi::c_void;
    use std::sync::atomic::{AtomicIsize, Ordering};

    use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, HANDLE, HWND, POINT, RECT};
    use windows_sys::Win32::Graphics::Gdi::{GetMonitorInfoW, MonitorFromWindow, MONITORINFO, MONITOR_DEFAULTTONEAREST};
    use windows_sys::Win32::Security::{GetTokenInformation, TokenElevation, TOKEN_ELEVATION, TOKEN_QUERY};
    use windows_sys::Win32::System::LibraryLoader::{GetModuleHandleW, GetProcAddress};
    use windows_sys::Win32::System::SystemInformation::OSVERSIONINFOW;
    use windows_sys::Win32::System::Threading::{
        GetCurrentProcess, GetCurrentProcessId, OpenProcess, OpenProcessToken, QueryFullProcessImageNameW,
        PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetAncestor, GetClassNameW, GetCursorPos, GetForegroundWindow, GetWindow, GetWindowLongW, GetWindowRect,
        GetWindowThreadProcessId, IsWindowVisible, WindowFromPoint, GA_ROOT, GWL_EXSTYLE, GW_HWNDNEXT, WS_EX_TOPMOST,
        WS_EX_TRANSPARENT,
    };

    static OVERLAY: AtomicIsize = AtomicIsize::new(0);

    pub fn set_overlay(hwnd: isize) {
        OVERLAY.store(hwnd, Ordering::Relaxed);
    }

    fn overlay() -> HWND {
        OVERLAY.load(Ordering::Relaxed) as HWND
    }

    fn yes(b: bool) -> &'static str {
        if b {
            "yes"
        } else {
            "no"
        }
    }

    unsafe fn exstyle(hwnd: HWND) -> u32 {
        unsafe { GetWindowLongW(hwnd, GWL_EXSTYLE) as u32 }
    }

    pub fn overlay_passes() -> Option<bool> {
        let h = overlay();
        (!h.is_null()).then(|| (unsafe { exstyle(h) } & WS_EX_TRANSPARENT) != 0)
    }

    /// File name of process `pid`, or `pid:N (open error E)` when it cannot be opened.
    fn process_name(pid: u32) -> String {
        unsafe {
            let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if process.is_null() {
                return format!("pid:{pid} (open error {})", GetLastError());
            }
            let name = exe_name(process).unwrap_or_else(|| format!("pid:{pid}"));
            CloseHandle(process);
            name
        }
    }

    unsafe fn class_name(hwnd: HWND) -> String {
        let mut buf = [0u16; 128];
        let len = unsafe { GetClassNameW(hwnd, buf.as_mut_ptr(), buf.len() as i32) };
        String::from_utf16_lossy(&buf[..len.max(0) as usize])
    }

    /// Where the pet window sits relative to `fg` in the z-order.
    unsafe fn pet_order(fg: HWND) -> &'static str {
        let pet = overlay();
        if pet.is_null() {
            return "unknown";
        }
        if pet == fg {
            return "is foreground";
        }
        unsafe {
            let mut h = GetWindow(pet, GW_HWNDNEXT);
            for _ in 0..8192 {
                if h.is_null() {
                    break;
                }
                if h == fg {
                    return "above";
                }
                h = GetWindow(h, GW_HWNDNEXT);
            }
        }
        "below"
    }

    /// Changes when the foreground window or the pet window's place relative to it does.
    pub fn foreground_key() -> String {
        unsafe {
            let fg = GetForegroundWindow();
            format!("{:?} {}", fg, if fg.is_null() { "" } else { pet_order(fg) })
        }
    }

    pub fn foreground_detail() -> String {
        unsafe {
            let fg = GetForegroundWindow();
            if fg.is_null() {
                return "fg=none".into();
            }
            let mut pid = 0u32;
            GetWindowThreadProcessId(fg, &mut pid);
            let mut out = foreground();
            if out.contains("elevated=?") && pid != GetCurrentProcessId() {
                out.push_str(&format!(" ({})", process_name(pid)));
            }
            let mut r = RECT { left: 0, top: 0, right: 0, bottom: 0 };
            GetWindowRect(fg, &mut r);
            let pet = overlay();
            let pet_state = if pet.is_null() {
                String::new()
            } else {
                format!(
                    ", pet window visible={} topmost={}",
                    yes(IsWindowVisible(pet) != 0),
                    yes(exstyle(pet) & WS_EX_TOPMOST != 0)
                )
            };
            out.push_str(&format!(
                " class={} topmost={} rect={}x{}+{}+{}; pet window {} it{pet_state}",
                class_name(fg),
                yes(exstyle(fg) & WS_EX_TOPMOST != 0),
                r.right - r.left,
                r.bottom - r.top,
                r.left,
                r.top,
                pet_order(fg)
            ));
            out
        }
    }

    pub fn under_cursor() -> String {
        unsafe {
            let mut pt = POINT { x: 0, y: 0 };
            if GetCursorPos(&mut pt) == 0 {
                return format!("cursor unavailable (error {})", GetLastError());
            }
            let hit = WindowFromPoint(pt);
            let root = if hit.is_null() { hit } else { GetAncestor(hit, GA_ROOT) };
            let under = if root.is_null() {
                "none".to_string()
            } else if root == overlay() {
                "pet window".to_string()
            } else {
                let mut pid = 0u32;
                GetWindowThreadProcessId(root, &mut pid);
                if pid == GetCurrentProcessId() {
                    "panel".to_string()
                } else {
                    process_name(pid)
                }
            };
            format!("cursor=({},{}) under={under}", pt.x, pt.y)
        }
    }

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
            let full = if covers_monitor(hwnd) { " fullscreen" } else { "" };
            if pid == GetCurrentProcessId() {
                return format!("fg=self{full}");
            }
            match process_info(pid) {
                Some((name, elevated)) => {
                    let elevated = match elevated {
                        Some(true) => "yes",
                        Some(false) => "no",
                        None => "?",
                    };
                    format!("fg={name}{full} elevated={elevated}")
                }
                None => format!("fg=pid:{pid}{full} elevated=?"),
            }
        }
    }

    /// File name of process `pid` and whether it runs elevated; None when it cannot be opened.
    fn process_info(pid: u32) -> Option<(String, Option<bool>)> {
        if pid == 0 {
            return None;
        }
        unsafe {
            let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if process.is_null() {
                return None;
            }
            let name = exe_name(process).unwrap_or_else(|| format!("pid:{pid}"));
            let elevated = token_elevated(process);
            CloseHandle(process);
            Some((name, elevated))
        }
    }

    /// The foreground program's file name and whether it surely runs elevated; None for
    /// no foreground window, our own, or a process that cannot be opened.
    pub fn foreground_process() -> Option<(String, bool)> {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.is_null() {
                return None;
            }
            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, &mut pid);
            if pid == GetCurrentProcessId() {
                return None;
            }
            let (name, elevated) = process_info(pid)?;
            Some((name, elevated == Some(true)))
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

    #[allow(dead_code)]
    pub fn set_overlay(_hwnd: isize) {}

    pub fn overlay_passes() -> Option<bool> {
        None
    }

    pub fn foreground_key() -> String {
        String::new()
    }

    pub fn foreground_detail() -> String {
        foreground()
    }

    pub fn under_cursor() -> String {
        "cursor=n/a".into()
    }
}
