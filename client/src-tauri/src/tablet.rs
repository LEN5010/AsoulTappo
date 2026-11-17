//! Pen tablets on Windows.
//!
//! A pen in Windows Ink mode is pointer input: the system moves the cursor and sends the window under it pointer
//! messages, and none of it passes the low-level mouse hook (src/input.rs), so the pet would neither see the pen
//! move nor count its taps. This module reads the tablet's own HID reports through Raw Input (digitizer usage page,
//! registered with RIDEV_INPUTSINK so they arrive whichever window is in front) and turns them into what the hook
//! gives for a mouse: the cursor's position on every report, a left press when the tip touches down and a release
//! when it lifts. Only the tip switch is read from a report; where the pen is comes from the cursor.
//!
//! A tablet driver in mouse mode (Windows Ink off, or a driver that sends its own mouse input) already reaches the
//! hook. Its tap would count twice if the tablet's reports still arrived here, so a tip-down is held for `ECHO_MS`
//! and dropped when the hook saw a left press around the same moment.
//!
//! PRIVACY: as the hook, this forwards that a press happened and where the cursor is, never what was drawn.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;
use std::time::Instant;

/// A tip-down waits this long (ms) for the same tap to show up at the mouse hook before it counts as a press.
pub const ECHO_MS: u64 = 30;

/// No left press seen yet.
const NEVER: u64 = u64::MAX;
static MOUSE_LEFT_DOWN: AtomicU64 = AtomicU64::new(NEVER);
static START: OnceLock<Instant> = OnceLock::new();

/// Milliseconds on this module's own clock.
pub fn now_ms() -> u64 {
    START.get_or_init(Instant::now).elapsed().as_millis() as u64
}

/// The mouse hook saw a left button press.
pub fn note_mouse_left_down() {
    MOUSE_LEFT_DOWN.store(now_ms(), Ordering::Relaxed);
}

/// When the mouse hook last saw a left press, on now_ms()'s clock.
fn mouse_left_down() -> Option<u64> {
    match MOUSE_LEFT_DOWN.load(Ordering::Relaxed) {
        NEVER => None,
        at => Some(at),
    }
}

/// What a pen report adds to the input stream: a press, a release, or both for a tap shorter than `ECHO_MS`.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct PenOut {
    pub down: bool,
    pub up: bool,
}

/// The tip switch over successive reports, as presses the mouse hook has not already counted.
#[derive(Default)]
pub struct PenState {
    tip: bool,
    /// A tip-down not yet counted, and when it happened.
    pending: Option<u64>,
    /// A press went out and its release is owed.
    pressed: bool,
}

impl PenState {
    /// One report: whether the tip is down at `now`, and when the mouse hook last saw a left press (same clock).
    pub fn report(&mut self, tip: bool, now: u64, mouse_down: Option<u64>) -> PenOut {
        let mut out = PenOut::default();
        if tip && !self.tip {
            self.pending = Some(now);
        }
        if let Some(since) = self.pending {
            let echoed = mouse_down.is_some_and(|at| at.abs_diff(since) <= ECHO_MS);
            if echoed {
                // The driver sent this tap as a mouse press too: the hook has it.
                self.pending = None;
            } else if !tip || now.saturating_sub(since) >= ECHO_MS {
                self.pending = None;
                self.pressed = true;
                out.down = true;
            }
        }
        if !tip && self.pressed {
            self.pressed = false;
            out.up = true;
        }
        self.tip = tip;
        out
    }
}

#[cfg(target_os = "windows")]
pub use win::run;

#[cfg(target_os = "windows")]
mod win {
    use std::collections::HashMap;
    use std::mem::size_of;

    use rdev::{Button, EventType};
    use windows_sys::Win32::Devices::HumanInterfaceDevice::{HidP_GetUsages, HidP_Input, HIDP_STATUS_SUCCESS};
    use windows_sys::Win32::Foundation::{GetLastError, HANDLE, POINT};
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::UI::Input::{
        GetRawInputData, GetRawInputDeviceInfoW, RegisterRawInputDevices, HRAWINPUT, RAWINPUT, RAWINPUTDEVICE,
        RAWINPUTHEADER, RIDEV_INPUTSINK, RIDI_PREPARSEDDATA, RID_INPUT, RIM_TYPEHID,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DestroyWindow, DispatchMessageW, GetCursorPos, GetMessageW, HWND_MESSAGE, MSG, WM_INPUT,
    };

    use super::{mouse_left_down, now_ms, PenState};

    /// HID usage page Digitizers, its top-level collections Digitizer and Pen, and the usages Tip Switch and Eraser.
    const PAGE_DIGITIZER: u16 = 0x0D;
    const USAGE_DIGITIZER: u16 = 0x01;
    const USAGE_PEN: u16 = 0x02;
    const USAGE_TIP: u16 = 0x42;
    const USAGE_ERASER: u16 = 0x45;
    /// Buttons a report can have down at once; a pen has a handful.
    const MAX_USAGES: usize = 16;
    /// Tablets whose report layout is kept; beyond this the cache starts over.
    const MAX_DEVICES: usize = 16;

    /// A buffer the system fills with a struct of pointer alignment.
    fn buffer(bytes: u32) -> Vec<u64> {
        vec![0u64; (bytes as usize).div_ceil(size_of::<u64>())]
    }

    /// The report layout of a device (its HID preparsed data), read once.
    fn preparsed(cache: &mut HashMap<isize, Vec<u64>>, device: HANDLE) -> Option<&Vec<u64>> {
        let key = device as isize;
        if !cache.contains_key(&key) {
            if cache.len() >= MAX_DEVICES {
                cache.clear();
            }
            let mut size = 0u32;
            unsafe { GetRawInputDeviceInfoW(device, RIDI_PREPARSEDDATA, std::ptr::null_mut(), &mut size) };
            if size == 0 {
                return None;
            }
            let mut data = buffer(size);
            let got = unsafe { GetRawInputDeviceInfoW(device, RIDI_PREPARSEDDATA, data.as_mut_ptr().cast(), &mut size) };
            if got == u32::MAX || got == 0 {
                return None;
            }
            cache.insert(key, data);
        }
        cache.get(&key)
    }

    /// Whether the tip (or the eraser) is down in one report; None when the report has no digitizer buttons.
    fn tip_down(layout: &[u64], report: &[u8]) -> Option<bool> {
        let mut usages = [0u16; MAX_USAGES];
        let mut count = MAX_USAGES as u32;
        let status = unsafe {
            HidP_GetUsages(
                HidP_Input,
                PAGE_DIGITIZER,
                0,
                usages.as_mut_ptr(),
                &mut count,
                layout.as_ptr() as isize,
                report.as_ptr() as *mut u8,
                report.len() as u32,
            )
        };
        (status == HIDP_STATUS_SUCCESS)
            .then(|| usages[..count as usize].iter().any(|u| *u == USAGE_TIP || *u == USAGE_ERASER))
    }

    /// The tip switch of every report in one WM_INPUT, oldest first.
    fn tips(cache: &mut HashMap<isize, Vec<u64>>, input: HRAWINPUT) -> Vec<bool> {
        let header = size_of::<RAWINPUTHEADER>() as u32;
        let mut size = 0u32;
        unsafe { GetRawInputData(input, RID_INPUT, std::ptr::null_mut(), &mut size, header) };
        if size <= header {
            return Vec::new();
        }
        // A short HID report makes the input smaller than RAWINPUT, whose union is as large as its mouse variant.
        let mut data = buffer(size.max(size_of::<RAWINPUT>() as u32));
        let got = unsafe { GetRawInputData(input, RID_INPUT, data.as_mut_ptr().cast(), &mut size, header) };
        if got == u32::MAX || got <= header || got as usize > data.len() * size_of::<u64>() {
            return Vec::new();
        }
        let raw = data.as_ptr().cast::<RAWINPUT>();
        // SAFETY: the buffer is at least a RAWINPUT long and aligned for it; the reports follow the HID header inside it.
        let (device, len, count, first) = unsafe {
            if (*raw).header.dwType != RIM_TYPEHID {
                return Vec::new();
            }
            let hid = &(*raw).data.hid;
            (
                (*raw).header.hDevice,
                hid.dwSizeHid as usize,
                hid.dwCount as usize,
                hid.bRawData.as_ptr(),
            )
        };
        let offset = first as usize - data.as_ptr() as usize;
        if len == 0 || offset + len * count > got as usize {
            return Vec::new();
        }
        let Some(layout) = preparsed(cache, device) else { return Vec::new() };
        (0..count)
            // SAFETY: checked above that every report lies inside the bytes the system wrote.
            .filter_map(|i| tip_down(layout, unsafe { std::slice::from_raw_parts(first.add(i * len), len) }))
            .collect()
    }

    /// Reads pen reports on this thread until its message loop ends: `push` gets the cursor's position for every
    /// report and a left button press or release for the tip, marked as not injected.
    pub fn run(mut push: impl FnMut(EventType, Option<bool>)) -> Result<(), String> {
        // "STATIC" in UTF-16: a system window class, so none has to be registered for a window that only receives.
        let class: Vec<u16> = "STATIC\0".encode_utf16().collect();
        let window = unsafe {
            CreateWindowExW(
                0,
                class.as_ptr(),
                std::ptr::null(),
                0,
                0,
                0,
                0,
                0,
                HWND_MESSAGE,
                std::ptr::null_mut(),
                GetModuleHandleW(std::ptr::null()),
                std::ptr::null(),
            )
        };
        if window.is_null() {
            return Err(format!("message window error {}", unsafe { GetLastError() }));
        }
        let devices = [USAGE_PEN, USAGE_DIGITIZER].map(|usage| RAWINPUTDEVICE {
            usUsagePage: PAGE_DIGITIZER,
            usUsage: usage,
            dwFlags: RIDEV_INPUTSINK,
            hwndTarget: window,
        });
        let registered =
            unsafe { RegisterRawInputDevices(devices.as_ptr(), devices.len() as u32, size_of::<RAWINPUTDEVICE>() as u32) };
        if registered == 0 {
            let error = unsafe { GetLastError() };
            unsafe { DestroyWindow(window) };
            return Err(format!("raw input registration error {error}"));
        }
        applog!("tablet", "listening for pen reports");

        let mut cache = HashMap::new();
        let mut pen = PenState::default();
        let mut heard = false;
        let mut msg: MSG = unsafe { std::mem::zeroed() };
        while unsafe { GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) } > 0 {
            if msg.message == WM_INPUT {
                for tip in tips(&mut cache, msg.lParam as HRAWINPUT) {
                    if !heard {
                        heard = true;
                        applog!("tablet", "first pen report");
                    }
                    let mut at = POINT { x: 0, y: 0 };
                    if unsafe { GetCursorPos(&mut at) } != 0 {
                        push(EventType::MouseMove { x: at.x as f64, y: at.y as f64 }, None);
                    }
                    let out = pen.report(tip, now_ms(), mouse_left_down());
                    if out.down {
                        push(EventType::ButtonPress(Button::Left), Some(false));
                    }
                    if out.up {
                        push(EventType::ButtonRelease(Button::Left), Some(false));
                    }
                }
            }
            // The window's own procedure lets the system release the raw input.
            unsafe { DispatchMessageW(&msg) };
        }
        unsafe { DestroyWindow(window) };
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_tip_down_counts_once_the_hook_has_not_echoed_it() {
        let mut pen = PenState::default();
        assert_eq!(pen.report(false, 0, None), PenOut::default());
        assert_eq!(pen.report(true, 100, None), PenOut::default());
        assert_eq!(pen.report(true, 110, None), PenOut::default());
        assert_eq!(pen.report(true, 100 + ECHO_MS, None), PenOut { down: true, up: false });
        // Held: nothing more until it lifts.
        assert_eq!(pen.report(true, 400, None), PenOut::default());
        assert_eq!(pen.report(false, 500, None), PenOut { down: false, up: true });
        assert_eq!(pen.report(false, 510, None), PenOut::default());
    }

    #[test]
    fn a_tap_the_mouse_hook_also_saw_is_left_to_the_hook() {
        // The hook's press a little after the tip-down, and a little before.
        for mouse in [108, 95] {
            let mut pen = PenState::default();
            assert_eq!(pen.report(true, 100, None), PenOut::default());
            assert_eq!(pen.report(true, 110, Some(mouse)), PenOut::default());
            assert_eq!(pen.report(true, 200, Some(mouse)), PenOut::default());
            assert_eq!(pen.report(false, 300, Some(mouse)), PenOut::default());
        }
    }

    #[test]
    fn an_old_mouse_press_does_not_hide_a_pen_tap() {
        let mut pen = PenState::default();
        assert_eq!(pen.report(true, 5_000, Some(100)), PenOut::default());
        assert_eq!(pen.report(true, 5_000 + ECHO_MS, Some(100)), PenOut { down: true, up: false });
    }

    #[test]
    fn a_tap_shorter_than_the_wait_is_a_press_and_a_release() {
        let mut pen = PenState::default();
        assert_eq!(pen.report(true, 100, None), PenOut::default());
        assert_eq!(pen.report(false, 110, None), PenOut { down: true, up: true });
        // Unless the hook had it.
        assert_eq!(pen.report(true, 300, None), PenOut::default());
        assert_eq!(pen.report(false, 310, Some(305)), PenOut::default());
    }

    #[test]
    fn every_tap_counts_on_its_own() {
        let mut pen = PenState::default();
        let mut downs = 0;
        for k in 0..5u64 {
            let t = 1_000 * k;
            downs += u32::from(pen.report(true, t, None).down);
            downs += u32::from(pen.report(true, t + 40, None).down);
            assert!(pen.report(false, t + 80, None).up);
        }
        assert_eq!(downs, 5);
    }
}
