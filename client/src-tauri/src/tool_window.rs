//! Keeps the desk overlay out of other apps' occlusion checks (Windows).
//!
//! The overlay covers the whole work area. With the cursor on a pet it stops ignoring the cursor,
//! and tao drops WS_EX_TRANSPARENT and WS_EX_LAYERED with that. Chromium browsers and Electron apps
//! then take the overlay for an opaque window covering them, mark themselves occluded and stop
//! painting: a playing stream turns white. Their check skips tool windows
//! (`gfx::IsWindowVisibleAndFullyOpaque`, ui/gfx/win/hwnd_util.cc), so the overlay is made one.
//!
//! tao rewrites the whole extended style whenever one of its window flags changes (cursor
//! pass-through, focusable, visible), so a subclass puts the bit back into every new extended style.
//! tao also sets WS_EX_APPWINDOW on top-level windows, which keeps the overlay in Alt+Tab as before.

use windows_sys::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
use windows_sys::Win32::UI::Shell::{DefSubclassProc, SetWindowSubclass};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    GetWindowLongW, SetWindowLongW, SetWindowPos, GWL_EXSTYLE, STYLESTRUCT, SWP_FRAMECHANGED, SWP_NOACTIVATE,
    SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, WM_STYLECHANGING, WS_EX_TOOLWINDOW,
};

const SUBCLASS_ID: usize = 0x7461_7070;

unsafe extern "system" fn keep_tool_window(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
    _id: usize,
    _data: usize,
) -> LRESULT {
    // wParam carries GWL_EXSTYLE (-20) sign-extended; lParam points at the old and new styles.
    if msg == WM_STYLECHANGING && wparam as i32 == GWL_EXSTYLE && lparam != 0 {
        let styles = unsafe { &mut *(lparam as *mut STYLESTRUCT) };
        styles.styleNew |= WS_EX_TOOLWINDOW;
    }
    unsafe { DefSubclassProc(hwnd, msg, wparam, lparam) }
}

/// Make `window` a tool window for good. Must run on the thread that created it (Tauri's main
/// thread, e.g. in `setup`). Returns false when the subclass could not be installed.
pub fn keep(window: &tauri::WebviewWindow) -> tauri::Result<bool> {
    let hwnd: HWND = window.hwnd()?.0;
    unsafe {
        if SetWindowSubclass(hwnd, Some(keep_tool_window), SUBCLASS_ID, 0) == 0 {
            return Ok(false);
        }
        SetWindowLongW(hwnd, GWL_EXSTYLE, GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW as i32);
        SetWindowPos(
            hwnd,
            std::ptr::null_mut(),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );
    }
    Ok(true)
}
