//! Pen tablets on Windows.
//!
//! A pen in Windows Ink mode is pointer input: the system moves the cursor itself and sends the window under it
//! pointer messages, so the low-level mouse hook (src/input.rs) never sees the pen move. Its taps do reach the hook,
//! as mouse presses the system sends on the pen's behalf (`0xFF515700` in their extra info) with the injected flag a
//! clicker's presses have (src/input.rs, AUTOMATED INPUT); with press-and-hold on, a tap's press may come only when
//! the pen lifts, and a hold comes as a right click. This module reads the tablet's own HID reports through Raw
//! Input (digitizer usage page, registered with RIDEV_INPUTSINK so they arrive whichever window is in front) and
//! turns them into what the hook gives for a mouse: the cursor's position on every report, a left press when the tip
//! touches down and a release when it lifts. Only the tip switch is read from a report; where the pen is comes from
//! the cursor.
//!
//! While a tablet is sending reports (`PEN_LIVE_MS`), mouse button presses with the injected flag are dropped
//! together with their releases (`PenGate`), and the pen's taps count from its reports instead: the presses that
//! Windows Ink or a driver's `SendInput` sends for the pen neither count twice nor count as software's. Dropping
//! only takes presses away, so it gives a clicker nothing. Without a tablet sending reports no press is changed.
//!
//! A tablet driver in mouse mode (Windows Ink off) that sends its taps as ordinary mouse input already reaches the
//! hook. Its tap would count twice if the tablet's reports still arrived here, so a tip-down is held for `ECHO_MS`
//! and dropped when the hook passed on a left press around the same moment.
//!
//! PRIVACY: as the hook, this forwards that a press happened and where the cursor is, never what was drawn.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;
use std::time::Instant;

use rdev::{Button, EventType};

/// A tip-down waits this long (ms) for the same tap to show up at the mouse hook before it counts as a press.
pub const ECHO_MS: u64 = 30;

/// A pen counts as in use this long (ms) after its tablet's last report. A tablet reports many times a second while
/// the pen is near it, touching or not.
pub const PEN_LIVE_MS: u64 = 2000;

/// Not seen yet.
const NEVER: u64 = u64::MAX;
static MOUSE_LEFT_DOWN: AtomicU64 = AtomicU64::new(NEVER);
static PEN_REPORT: AtomicU64 = AtomicU64::new(NEVER);
static TIP_DOWN: AtomicU64 = AtomicU64::new(NEVER);
static TIP_UP: AtomicU64 = AtomicU64::new(NEVER);
static START: OnceLock<Instant> = OnceLock::new();

/// Milliseconds on this module's own clock.
pub fn now_ms() -> u64 {
    START.get_or_init(Instant::now).elapsed().as_millis() as u64
}

fn load(at: &AtomicU64) -> Option<u64> {
    match at.load(Ordering::Relaxed) {
        NEVER => None,
        at => Some(at),
    }
}

/// A left press from the mouse hook was passed on (not dropped by `PenGate`).
pub fn note_mouse_left_down() {
    MOUSE_LEFT_DOWN.store(now_ms(), Ordering::Relaxed);
}

/// When a left press from the mouse hook was last passed on, on now_ms()'s clock.
fn mouse_left_down() -> Option<u64> {
    load(&MOUSE_LEFT_DOWN)
}

/// A tablet report arrived at [now]: [tip] is whether the tip (or the eraser) is down, [was] whether it was before.
pub fn note_pen_report(tip: bool, was: bool, now: u64) {
    PEN_REPORT.store(now, Ordering::Relaxed);
    if tip && !was {
        TIP_DOWN.store(now, Ordering::Relaxed);
    } else if !tip && was {
        TIP_UP.store(now, Ordering::Relaxed);
    }
}

/// When a tablet last sent a report, its tip last touched down and last lifted, on now_ms()'s clock.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct PenTimes {
    pub report: Option<u64>,
    pub tip_down: Option<u64>,
    pub tip_up: Option<u64>,
}

pub fn pen_times() -> PenTimes {
    PenTimes { report: load(&PEN_REPORT), tip_down: load(&TIP_DOWN), tip_up: load(&TIP_UP) }
}

/// Whether a pen is in use at [now], given its tablet's last report. The report thread may have stored a time a
/// little after [now] was read.
pub fn pen_live(report: Option<u64>, now: u64) -> bool {
    report.is_some_and(|at| now.saturating_sub(at) <= PEN_LIVE_MS)
}

/// Drops software's mouse button presses while a pen is in use, each with its release, whatever button it is.
#[derive(Default)]
pub struct PenGate {
    /// Buttons whose last press was dropped: their release goes too.
    dropped: Vec<Button>,
}

impl PenGate {
    /// Whether one event from the mouse hook goes on. [injected]: the press's or release's injected flag;
    /// [live]: whether a pen is in use (`pen_live`).
    pub fn pass(&mut self, event: &EventType, injected: Option<bool>, live: bool) -> bool {
        match event {
            EventType::ButtonPress(b) => {
                self.dropped.retain(|d| d != b);
                if injected == Some(true) && live {
                    self.dropped.push(*b);
                    false
                } else {
                    true
                }
            }
            EventType::ButtonRelease(b) => {
                let before = self.dropped.len();
                self.dropped.retain(|d| d != b);
                self.dropped.len() == before
            }
            _ => true,
        }
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
        GetRawInputData, GetRawInputDeviceInfoW, GetRawInputDeviceList, RegisterRawInputDevices, HRAWINPUT, RAWINPUT,
        RAWINPUTDEVICE, RAWINPUTDEVICELIST, RAWINPUTHEADER, RIDEV_INPUTSINK, RIDI_DEVICEINFO, RIDI_PREPARSEDDATA,
        RID_DEVICE_INFO, RID_INPUT, RIM_TYPEHID,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DestroyWindow, DispatchMessageW, GetCursorPos, GetMessageW, HWND_MESSAGE, MSG, WM_INPUT,
    };

    use super::{mouse_left_down, note_pen_report, now_ms, PenState};

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

    /// The HID devices present, as usage page/usage and vendor:product ids, so a log shows what a tablet offers when
    /// its pen reports never arrive here. Kinds and ids only, never device names.
    fn hid_devices() -> String {
        let item = size_of::<RAWINPUTDEVICELIST>() as u32;
        let mut count = 0u32;
        if unsafe { GetRawInputDeviceList(std::ptr::null_mut(), &mut count, item) } == u32::MAX || count == 0 {
            return "none".to_string();
        }
        let mut list = vec![RAWINPUTDEVICELIST { hDevice: std::ptr::null_mut(), dwType: 0 }; count as usize];
        let got = unsafe { GetRawInputDeviceList(list.as_mut_ptr(), &mut count, item) };
        if got == u32::MAX {
            return "unknown".to_string();
        }
        let mut seen: Vec<String> = list
            .iter()
            .take(got as usize)
            .filter(|device| device.dwType == RIM_TYPEHID)
            .filter_map(|device| {
                let mut info = RID_DEVICE_INFO { cbSize: size_of::<RID_DEVICE_INFO>() as u32, ..Default::default() };
                let mut size = info.cbSize;
                let read = unsafe {
                    GetRawInputDeviceInfoW(
                        device.hDevice,
                        RIDI_DEVICEINFO,
                        (&mut info as *mut RID_DEVICE_INFO).cast(),
                        &mut size,
                    )
                };
                if read == u32::MAX || read == 0 || info.dwType != RIM_TYPEHID {
                    return None;
                }
                // SAFETY: dwType says the union holds its HID variant.
                let hid = unsafe { info.Anonymous.hid };
                Some(format!(
                    "{:02X}/{:02X} {:04X}:{:04X}",
                    hid.usUsagePage, hid.usUsage, hid.dwVendorId, hid.dwProductId
                ))
            })
            .collect();
        seen.sort();
        seen.dedup();
        if seen.is_empty() {
            "none".to_string()
        } else {
            seen.join(", ")
        }
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
        applog!("tablet", "listening for pen reports; HID devices: {}", hid_devices());

        let mut cache = HashMap::new();
        let mut pen = PenState::default();
        let mut heard = false;
        let mut last_tip = false;
        let mut msg: MSG = unsafe { std::mem::zeroed() };
        while unsafe { GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) } > 0 {
            if msg.message == WM_INPUT {
                for tip in tips(&mut cache, msg.lParam as HRAWINPUT) {
                    if !heard {
                        heard = true;
                        applog!("tablet", "first pen report");
                    }
                    let now = now_ms();
                    note_pen_report(tip, last_tip, now);
                    last_tip = tip;
                    let mut at = POINT { x: 0, y: 0 };
                    if unsafe { GetCursorPos(&mut at) } != 0 {
                        push(EventType::MouseMove { x: at.x as f64, y: at.y as f64 }, None);
                    }
                    let out = pen.report(tip, now, mouse_left_down());
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

    const DOWN: EventType = EventType::ButtonPress(Button::Left);
    const UP: EventType = EventType::ButtonRelease(Button::Left);
    const RIGHT_DOWN: EventType = EventType::ButtonPress(Button::Right);
    const RIGHT_UP: EventType = EventType::ButtonRelease(Button::Right);

    #[test]
    fn a_pen_is_in_use_until_its_tablet_goes_quiet() {
        assert!(!pen_live(None, 5_000));
        assert!(pen_live(Some(5_000), 5_000));
        assert!(pen_live(Some(5_000), 5_000 + PEN_LIVE_MS));
        assert!(!pen_live(Some(5_000), 5_000 + PEN_LIVE_MS + 1));
        // The report thread stored a time just after this one was read.
        assert!(pen_live(Some(5_003), 5_000));
    }

    #[test]
    fn software_clicks_while_a_pen_is_in_use_go_with_their_releases() {
        let mut gate = PenGate::default();
        assert!(!gate.pass(&DOWN, Some(true), true));
        assert!(!gate.pass(&UP, Some(true), true));
        // Press-and-hold: the right click Windows sends when the pen lifts.
        assert!(!gate.pass(&RIGHT_DOWN, Some(true), true));
        assert!(!gate.pass(&RIGHT_UP, Some(true), true));
        let middle = EventType::ButtonPress(Button::Middle);
        assert!(!gate.pass(&middle, Some(true), true));
        assert!(!gate.pass(&EventType::ButtonRelease(Button::Middle), Some(true), true));
    }

    #[test]
    fn without_a_pen_software_clicks_pass_as_they_are() {
        let mut gate = PenGate::default();
        assert!(gate.pass(&DOWN, Some(true), false));
        assert!(gate.pass(&UP, Some(true), false));
    }

    #[test]
    fn hand_clicks_pass_while_a_pen_is_in_use() {
        let mut gate = PenGate::default();
        assert!(gate.pass(&DOWN, Some(false), true));
        assert!(gate.pass(&UP, Some(false), true));
        // macOS and Linux report no flag.
        assert!(gate.pass(&DOWN, None, true));
        assert!(gate.pass(&UP, None, true));
        assert!(gate.pass(&EventType::MouseMove { x: 1.0, y: 2.0 }, None, true));
    }

    #[test]
    fn a_release_follows_its_own_press() {
        let mut gate = PenGate::default();
        // Dropped while the pen was in use: its release goes too, even once the pen is put away.
        assert!(!gate.pass(&DOWN, Some(true), true));
        assert!(!gate.pass(&UP, Some(true), false));
        // Passed before the pen came near: its release passes too.
        assert!(gate.pass(&DOWN, Some(true), false));
        assert!(gate.pass(&UP, Some(true), true));
        // A hand press after a dropped one starts over; only one release goes.
        assert!(!gate.pass(&RIGHT_DOWN, Some(true), true));
        assert!(gate.pass(&RIGHT_DOWN, Some(false), true));
        assert!(gate.pass(&RIGHT_UP, Some(false), true));
    }

    #[test]
    fn report_times_mark_the_tip_edges() {
        // The statics are shared by every test, so only this one writes them.
        note_pen_report(false, false, 100);
        assert_eq!(pen_times(), PenTimes { report: Some(100), tip_down: None, tip_up: None });
        note_pen_report(true, false, 120);
        note_pen_report(true, true, 130);
        note_pen_report(false, true, 190);
        assert_eq!(pen_times(), PenTimes { report: Some(190), tip_down: Some(120), tip_up: Some(190) });
    }

    /// The tablet thread and the filter thread of src/input.rs, as far as a tap goes: what each lets through.
    #[derive(Default)]
    struct Tap {
        pen: PenState,
        gate: PenGate,
        last_report: Option<u64>,
        mouse_down: Option<u64>,
        counted: Vec<(EventType, Option<bool>)>,
    }

    impl Tap {
        fn report(&mut self, tip: bool, at: u64) {
            self.last_report = Some(at);
            let out = self.pen.report(tip, at, self.mouse_down);
            if out.down {
                self.counted.push((DOWN, Some(false)));
            }
            if out.up {
                self.counted.push((UP, Some(false)));
            }
        }

        fn hook(&mut self, ev: EventType, injected: bool, at: u64) {
            if self.gate.pass(&ev, Some(injected), pen_live(self.last_report, at)) {
                if ev == DOWN {
                    self.mouse_down = Some(at);
                }
                self.counted.push((ev, Some(injected)));
            }
        }
    }

    /// Windows Ink with press-and-hold on: the system's press and release come only when the pen lifts, flagged as
    /// injected. The tap counts once, from the tablet, as not injected.
    #[test]
    fn a_windows_ink_tap_counts_once_from_the_tablet() {
        let mut t = Tap::default();
        t.report(false, 90);
        t.report(true, 100);
        t.report(true, 100 + ECHO_MS);
        t.report(false, 180);
        t.hook(DOWN, true, 182);
        t.hook(UP, true, 183);
        t.report(false, 190);
        assert_eq!(t.counted, [(DOWN, Some(false)), (UP, Some(false))]);
    }

    /// The same with the system's press at the tip-down, before the tablet thread has read that report.
    #[test]
    fn a_press_ahead_of_the_tip_report_is_dropped_too() {
        let mut t = Tap::default();
        t.report(false, 90);
        t.hook(DOWN, true, 99);
        t.report(true, 100);
        t.report(true, 100 + ECHO_MS);
        t.hook(UP, true, 170);
        t.report(false, 171);
        assert_eq!(t.counted, [(DOWN, Some(false)), (UP, Some(false))]);
    }

    /// A driver in mouse mode sends the tap as an ordinary mouse press while its tablet still reports: the hook's
    /// press counts and the tablet's is dropped as its echo.
    #[test]
    fn a_hand_press_from_a_mouse_mode_driver_counts_once_from_the_hook() {
        let mut t = Tap::default();
        t.report(false, 90);
        t.report(true, 100);
        t.hook(DOWN, false, 102);
        t.report(true, 100 + ECHO_MS);
        t.report(false, 170);
        t.hook(UP, false, 171);
        assert_eq!(t.counted, [(DOWN, Some(false)), (UP, Some(false))]);
    }

    /// A clicker running while the pen lies on the tablet gets nothing; once the tablet goes quiet its clicks count
    /// as they are, injected.
    #[test]
    fn a_clicker_next_to_a_pen_gains_nothing() {
        let mut t = Tap::default();
        t.report(false, 0);
        for k in 1..=5u64 {
            t.hook(DOWN, true, k * 100);
            t.hook(UP, true, k * 100 + 20);
        }
        assert!(t.counted.is_empty());
        t.hook(DOWN, true, PEN_LIVE_MS + 1);
        assert_eq!(t.counted, [(DOWN, Some(true))]);
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
