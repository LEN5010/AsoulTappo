//! Global keyboard / mouse hook (own low-level hooks on Windows, `rdev` elsewhere).
//!
//! PRIVACY: this module never forwards *which* key was pressed. The frontend
//! only learns "a key went down/up", which mouse button, and relative mouse
//! movement (used to animate the local pet; never sent over the network).

use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::mpsc::Sender;
use std::time::{Duration, Instant};

use rdev::{Button, EventType, Key};
use serde::Serialize;

#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MouseButton {
    Left,
    Right,
    Middle,
    Other,
}

#[derive(Serialize, Clone, Copy, Debug, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum InputEvent {
    KeyDown,
    KeyUp,
    MouseDown { button: MouseButton },
    MouseUp { button: MouseButton },
    MouseMove { dx: f64, dy: f64 },
}

/// Minimum spacing between emitted mouse-move events (~60 Hz).
const MOVE_INTERVAL: Duration = Duration::from_millis(16);

/// A key held longer than this without any OS auto-repeat is treated as released:
/// its key-up was lost (secure desktop, UAC prompt, lock screen, another hook).
const STUCK_KEY: Duration = Duration::from_millis(1500);

/// Pure state machine: raw rdev events in, privacy-filtered events out.
/// Kept separate from the hook thread so it is unit-testable.
#[derive(Default)]
pub struct InputState {
    /// Held keys and when the OS last reported them down (auto-repeat refreshes it).
    held: HashMap<Key, Instant>,
    last_pos: Option<(f64, f64)>,
    acc: (f64, f64),
    last_move_emit: Option<Instant>,
}

impl InputState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn handle(&mut self, ev: &EventType, now: Instant) -> Option<InputEvent> {
        match ev {
            // OS auto-repeat sends repeated presses: only report the first.
            EventType::KeyPress(k) => {
                let fresh = self
                    .held
                    .get(k)
                    .map_or(true, |seen| now.duration_since(*seen) >= STUCK_KEY);
                self.held.insert(*k, now);
                fresh.then_some(InputEvent::KeyDown)
            }
            EventType::KeyRelease(k) => self.held.remove(k).map(|_| InputEvent::KeyUp),
            EventType::ButtonPress(b) => Some(InputEvent::MouseDown { button: map_button(b) }),
            EventType::ButtonRelease(b) => Some(InputEvent::MouseUp { button: map_button(b) }),
            EventType::MouseMove { x, y } => {
                if let Some((lx, ly)) = self.last_pos {
                    self.acc.0 += x - lx;
                    self.acc.1 += y - ly;
                }
                self.last_pos = Some((*x, *y));
                let due = self
                    .last_move_emit
                    .map_or(true, |t| now.duration_since(t) >= MOVE_INTERVAL);
                if due && (self.acc.0 != 0.0 || self.acc.1 != 0.0) {
                    let (dx, dy) = std::mem::take(&mut self.acc);
                    self.last_move_emit = Some(now);
                    Some(InputEvent::MouseMove { dx, dy })
                } else {
                    None
                }
            }
            EventType::Wheel { .. } => None,
        }
    }
}

fn map_button(b: &Button) -> MouseButton {
    match b {
        Button::Left => MouseButton::Left,
        Button::Right => MouseButton::Right,
        Button::Middle => MouseButton::Middle,
        Button::Unknown(_) => MouseButton::Other,
    }
}

/// Pause before installing the hook again after it failed (e.g. no accessibility
/// permission on macOS yet).
const RETRY: Duration = Duration::from_secs(5);

/// The system saw input this long (ms) after the hook last heard anything: the hook is gone.
const STALE_MS: i32 = 3000;

/// Raw mouse moves closer together than this are dropped at the hook.
const MOVE_COALESCE: Duration = Duration::from_millis(4);

/// How often a summary of what the hook heard goes to the log.
const STATS_EVERY: Duration = Duration::from_secs(60);

/// Filtered events emitted in the current stats interval (counts only).
static KEYS: AtomicU32 = AtomicU32::new(0);
static CLICKS: AtomicU32 = AtomicU32::new(0);
static MOVES: AtomicU32 = AtomicU32::new(0);

/// Spawn the global hook and the thread that filters its events; `emit` is called
/// for every filtered event.
///
/// The OS hook callback only timestamps the event and queues it: Windows silently
/// removes a low-level hook whose callback runs past `LowLevelHooksTimeout`, which
/// a busy fullscreen game easily causes if the callback does IPC itself. Filtering
/// and emitting happen on a separate thread.
///
/// Each hook gets a thread of its own. On Windows it unhooks and ends on WM_QUIT,
/// which is how the watchdog replaces a hook that went silent. rdev (macOS, Linux)
/// never unhooks; the OS removes a thread's hooks when the thread exits.
pub fn spawn_hook<F>(emit: F)
where
    F: Fn(InputEvent) + Send + 'static,
{
    let (tx, rx) = std::sync::mpsc::channel::<(EventType, Instant)>();

    std::thread::spawn(move || {
        let mut state = InputState::new();
        for (ev, at) in rx {
            if let Some(out) = state.handle(&ev, at) {
                let counter = match out {
                    InputEvent::KeyDown => Some(&KEYS),
                    InputEvent::MouseDown { .. } => Some(&CLICKS),
                    InputEvent::MouseMove { .. } => Some(&MOVES),
                    _ => None,
                };
                if let Some(counter) = counter {
                    counter.fetch_add(1, Ordering::Relaxed);
                }
                emit(out);
            }
        }
    });

    std::thread::spawn(move || loop {
        let hook = {
            let producer = Producer { tx: tx.clone(), last_move: None };
            std::thread::spawn(move || run_hook(producer))
        };
        if watchdog::watch(&hook) {
            // A thread that did not take its WM_QUIT is left behind: on Windows each hook
            // thread keeps its own state, so a new one can start next to it.
            if hook.is_finished() {
                let _ = hook.join();
            } else {
                applog!("hook", "old hook thread did not end; starting a new one anyway");
            }
        } else {
            let _ = hook.join();
            std::thread::sleep(RETRY);
        }
    });

    spawn_stats();
}

/// Once a minute, while anything happened, log what the hook heard next to what the
/// system saw and which window was in front. Counts only, never keys.
fn spawn_stats() {
    std::thread::spawn(|| loop {
        std::thread::sleep(STATS_EVERY);
        let keys = KEYS.swap(0, Ordering::Relaxed);
        let clicks = CLICKS.swap(0, Ordering::Relaxed);
        let moves = MOVES.swap(0, Ordering::Relaxed);
        let pad = crate::gamepad::take_presses();
        let replaced = watchdog::take_replaced();
        let age = watchdog::input_age_secs();
        let user_active = age.is_some_and(|s| s < STATS_EVERY.as_secs());
        if keys + clicks + moves + pad + replaced == 0 && !user_active {
            continue;
        }
        let system = age.map_or_else(|| "?".to_string(), |s| format!("{s}s"));
        applog!(
            "input",
            "last minute: keys {keys}, clicks {clicks}, moves {moves}, pad {pad}, hooks replaced {replaced}; \
             system input {system} ago; {}",
            crate::diag::foreground()
        );
    });
}

/// What a hook callback does with an event: note that the hook is alive, drop wheel
/// events, thin out mouse moves, queue the rest for the filter thread.
struct Producer {
    tx: Sender<(EventType, Instant)>,
    last_move: Option<Instant>,
}

impl Producer {
    fn push(&mut self, ev: EventType) {
        watchdog::heard();
        let now = Instant::now();
        match ev {
            EventType::Wheel { .. } => return,
            // High-polling mice can fire thousands of moves per second and an unbounded
            // queue would grow if the consumer stalls. Positions are absolute, so skipping
            // intermediate moves loses nothing. Key and button down/up are always queued.
            EventType::MouseMove { .. } => {
                if self.last_move.is_some_and(|t| now.duration_since(t) < MOVE_COALESCE) {
                    return;
                }
                self.last_move = Some(now);
            }
            _ => {}
        }
        let _ = self.tx.send((ev, now));
    }
}

/// Install the hook and pump its events until it stops.
fn run_hook(producer: Producer) {
    watchdog::enter();
    match listen(producer) {
        Ok(()) => applog!("hook", "hook thread ended"),
        Err(e) => applog!("hook", "could not install the hook: {e}; retrying in {}s", RETRY.as_secs()),
    }
}

#[cfg(target_os = "windows")]
fn listen(producer: Producer) -> Result<(), String> {
    win_hook::listen(producer)
}

#[cfg(not(target_os = "windows"))]
fn listen(mut producer: Producer) -> Result<(), String> {
    // rdev otherwise looks up the keyboard layout (TIS/TSM) on this thread for
    // every key, which macOS 14+ only allows on the main thread and aborts on.
    #[cfg(target_os = "macos")]
    rdev::set_is_main_thread(false);
    applog!("hook", "listening");
    rdev::listen(move |event| producer.push(event.event_type)).map_err(|e| format!("{e:?}"))
}

/// Plain low-level hooks whose callbacks only read the event and queue it.
///
/// rdev's Windows hook looked up a name for every key press inside the keyboard callback:
/// it attached this thread to the foreground thread's input queue (AttachThreadInput),
/// read its keyboard state and ran ToUnicodeEx, with a loop that retries while ToUnicodeEx
/// reports a dead key. None of that is needed to count presses, and all of it runs while
/// the system waits on the callback.
#[cfg(target_os = "windows")]
mod win_hook {
    use std::cell::RefCell;

    use rdev::{Button, EventType, Key};
    use windows_sys::Win32::Foundation::{GetLastError, LPARAM, LRESULT, WPARAM};
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CallNextHookEx, GetMessageW, SetWindowsHookExW, UnhookWindowsHookEx, HC_ACTION, KBDLLHOOKSTRUCT, MSG,
        MSLLHOOKSTRUCT, WH_KEYBOARD_LL, WH_MOUSE_LL, WM_KEYDOWN, WM_KEYUP, WM_LBUTTONDOWN, WM_LBUTTONUP,
        WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MOUSEMOVE, WM_RBUTTONDOWN, WM_RBUTTONUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
        WM_XBUTTONDOWN, WM_XBUTTONUP,
    };

    use super::Producer;

    thread_local! {
        /// The hook procedures run on the thread that installed them, inside its GetMessageW.
        static PRODUCER: RefCell<Option<Producer>> = const { RefCell::new(None) };
    }

    fn push(ev: EventType) {
        PRODUCER.with(|p| {
            if let Ok(mut p) = p.try_borrow_mut() {
                if let Some(p) = p.as_mut() {
                    p.push(ev);
                }
            }
        });
    }

    unsafe extern "system" fn keyboard(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
        if code == HC_ACTION as i32 && lparam != 0 {
            // The virtual-key code only tells auto-repeat apart from a new press; it never leaves this process.
            let vk = unsafe { (*(lparam as *const KBDLLHOOKSTRUCT)).vkCode };
            match wparam as u32 {
                WM_KEYDOWN | WM_SYSKEYDOWN => push(EventType::KeyPress(Key::Unknown(vk))),
                WM_KEYUP | WM_SYSKEYUP => push(EventType::KeyRelease(Key::Unknown(vk))),
                _ => {}
            }
        }
        unsafe { CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) }
    }

    unsafe extern "system" fn mouse(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
        if code == HC_ACTION as i32 && lparam != 0 {
            let info = unsafe { &*(lparam as *const MSLLHOOKSTRUCT) };
            let x_button = Button::Unknown((info.mouseData >> 16) as u8);
            let ev = match wparam as u32 {
                WM_MOUSEMOVE => Some(EventType::MouseMove { x: info.pt.x as f64, y: info.pt.y as f64 }),
                WM_LBUTTONDOWN => Some(EventType::ButtonPress(Button::Left)),
                WM_LBUTTONUP => Some(EventType::ButtonRelease(Button::Left)),
                WM_RBUTTONDOWN => Some(EventType::ButtonPress(Button::Right)),
                WM_RBUTTONUP => Some(EventType::ButtonRelease(Button::Right)),
                WM_MBUTTONDOWN => Some(EventType::ButtonPress(Button::Middle)),
                WM_MBUTTONUP => Some(EventType::ButtonRelease(Button::Middle)),
                WM_XBUTTONDOWN => Some(EventType::ButtonPress(x_button)),
                WM_XBUTTONUP => Some(EventType::ButtonRelease(x_button)),
                // Wheel events are not used.
                _ => None,
            };
            if let Some(ev) = ev {
                push(ev);
            }
        }
        unsafe { CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) }
    }

    /// Install both hooks on this thread and pump its messages until WM_QUIT, then unhook.
    pub fn listen(producer: Producer) -> Result<(), String> {
        PRODUCER.with(|p| *p.borrow_mut() = Some(producer));
        let result = unsafe {
            let module = GetModuleHandleW(std::ptr::null());
            let keyboard_hook = SetWindowsHookExW(WH_KEYBOARD_LL, Some(keyboard), module, 0);
            if keyboard_hook.is_null() {
                Err(format!("keyboard hook error {}", GetLastError()))
            } else {
                let mouse_hook = SetWindowsHookExW(WH_MOUSE_LL, Some(mouse), module, 0);
                if mouse_hook.is_null() {
                    let error = GetLastError();
                    UnhookWindowsHookEx(keyboard_hook);
                    Err(format!("mouse hook error {error}"))
                } else {
                    applog!("hook", "keyboard and mouse hooks installed");
                    let mut msg: MSG = std::mem::zeroed();
                    // 0 on WM_QUIT, -1 on error; other thread messages are skipped.
                    while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) > 0 {}
                    UnhookWindowsHookEx(mouse_hook);
                    UnhookWindowsHookEx(keyboard_hook);
                    Ok(())
                }
            }
        };
        PRODUCER.with(|p| *p.borrow_mut() = None);
        result
    }
}

/// Whether the system saw input more than `STALE_MS` after the hook last heard any.
/// Both are `GetTickCount` values, which wrap every 49.7 days.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
fn went_silent(last_input: u32, last_heard: u32) -> bool {
    last_input.wrapping_sub(last_heard) as i32 > STALE_MS
}

/// Windows drops a low-level hook without telling anyone. The system's own last-input
/// time keeps moving while the hook hears nothing; then the hook thread is ended and
/// `spawn_hook` installs a new one.
///
/// It also fires, harmlessly, while the hook is muted rather than gone: an elevated
/// window in front, the secure desktop (UAC, lock screen), pen or touch input that
/// never reaches the mouse hook. `MIN_LIFE` keeps that from replacing it on every check.
#[cfg(target_os = "windows")]
mod watchdog {
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::thread::JoinHandle;
    use std::time::{Duration, Instant};

    use windows_sys::Win32::System::SystemInformation::GetTickCount;
    use windows_sys::Win32::System::Threading::{
        GetCurrentThread, GetCurrentThreadId, SetThreadPriority, THREAD_PRIORITY_HIGHEST,
    };
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};
    use windows_sys::Win32::UI::WindowsAndMessaging::{PostThreadMessageW, WM_QUIT};

    const CHECK: Duration = Duration::from_secs(2);
    /// A hook lives at least this long before it may be replaced.
    const MIN_LIFE: Duration = Duration::from_secs(10);
    /// How long a silent hook thread gets to take its WM_QUIT before a new one starts anyway.
    const QUIT_WAIT: Duration = Duration::from_secs(2);

    static HOOK_THREAD: AtomicU32 = AtomicU32::new(0);
    static LAST_HEARD: AtomicU32 = AtomicU32::new(0);
    static REPLACED: AtomicU32 = AtomicU32::new(0);

    /// Called on the hook thread before it installs the hook.
    pub fn enter() {
        unsafe {
            HOOK_THREAD.store(GetCurrentThreadId(), Ordering::Release);
            LAST_HEARD.store(GetTickCount(), Ordering::Relaxed);
            // The thread sleeps in GetMessageW and its callbacks only read and queue, so a raised
            // priority costs little and keeps a game that saturates the CPU from pushing them past
            // the hook timeout. Not TIME_CRITICAL: if a callback ever spun, that would starve a core.
            SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);
        }
    }

    pub fn heard() {
        LAST_HEARD.store(unsafe { GetTickCount() }, Ordering::Relaxed);
    }

    /// Hooks replaced since the last call.
    pub fn take_replaced() -> u32 {
        REPLACED.swap(0, Ordering::Relaxed)
    }

    /// Seconds since the system last saw keyboard or mouse input.
    pub fn input_age_secs() -> Option<u64> {
        let last = last_input()?;
        Some(u64::from(unsafe { GetTickCount() }.wrapping_sub(last)) / 1000)
    }

    /// Wait for the hook thread to end; returns true when it was told to end for going silent.
    pub fn watch(hook: &JoinHandle<()>) -> bool {
        let started = Instant::now();
        while !hook.is_finished() {
            std::thread::sleep(CHECK);
            if started.elapsed() >= MIN_LIFE && missed_input() {
                let silent = last_input().map_or(0, |t| t.wrapping_sub(LAST_HEARD.load(Ordering::Relaxed)) / 1000);
                applog!(
                    "hook",
                    "heard nothing for {silent}s while the system saw input; replacing it; {}",
                    crate::diag::foreground()
                );
                REPLACED.fetch_add(1, Ordering::Relaxed);
                // WM_QUIT makes GetMessageW return, so the hook thread unhooks and ends.
                // Posting fails until the thread has a message queue: keep trying for a while.
                let id = HOOK_THREAD.load(Ordering::Acquire);
                let asked = Instant::now();
                while !hook.is_finished() && asked.elapsed() < QUIT_WAIT {
                    unsafe { PostThreadMessageW(id, WM_QUIT, 0, 0) };
                    std::thread::sleep(Duration::from_millis(100));
                }
                return true;
            }
        }
        false
    }

    fn last_input() -> Option<u32> {
        let mut info = LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };
        (unsafe { GetLastInputInfo(&mut info) } != 0).then_some(info.dwTime)
    }

    fn missed_input() -> bool {
        last_input().is_some_and(|t| super::went_silent(t, LAST_HEARD.load(Ordering::Relaxed)))
    }
}

/// Only Windows drops hooks silently; elsewhere this just waits for the hook thread.
#[cfg(not(target_os = "windows"))]
mod watchdog {
    pub fn enter() {}
    pub fn heard() {}
    pub fn take_replaced() -> u32 {
        0
    }
    pub fn input_age_secs() -> Option<u64> {
        None
    }
    pub fn watch(_hook: &std::thread::JoinHandle<()>) -> bool {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn key_autorepeat_is_deduplicated() {
        let mut s = InputState::new();
        let t = Instant::now();
        assert_eq!(s.handle(&EventType::KeyPress(Key::KeyA), t), Some(InputEvent::KeyDown));
        assert_eq!(s.handle(&EventType::KeyPress(Key::KeyA), t), None);
        assert_eq!(s.handle(&EventType::KeyRelease(Key::KeyA), t), Some(InputEvent::KeyUp));
        assert_eq!(s.handle(&EventType::KeyPress(Key::KeyA), t), Some(InputEvent::KeyDown));
    }

    #[test]
    fn a_key_whose_release_was_lost_counts_again() {
        let mut s = InputState::new();
        let t = Instant::now();
        assert_eq!(s.handle(&EventType::KeyPress(Key::KeyA), t), Some(InputEvent::KeyDown));
        // auto-repeat keeps refreshing the key, so it stays deduplicated
        let mut at = t;
        for _ in 0..100 {
            at += Duration::from_millis(33);
            assert_eq!(s.handle(&EventType::KeyPress(Key::KeyA), at), None);
        }
        // no event for a while: the key-up was lost, the next press is a new one
        let later = at + STUCK_KEY;
        assert_eq!(s.handle(&EventType::KeyPress(Key::KeyA), later), Some(InputEvent::KeyDown));
    }

    #[test]
    fn a_hook_is_silent_once_input_outruns_it() {
        assert!(!went_silent(1_000, 1_000));
        assert!(!went_silent(3_500, 1_000));
        assert!(went_silent(5_000, 1_000));
        // the hook heard something after the last input the system reports
        assert!(!went_silent(1_000, 5_000));
        // GetTickCount wrapped between the two
        assert!(went_silent(2_000, u32::MAX - 2_000));
        assert!(!went_silent(500, u32::MAX - 500));
    }

    #[test]
    fn serialized_key_events_carry_no_key_identity() {
        let json = serde_json::to_string(&InputEvent::KeyDown).unwrap();
        assert_eq!(json, r#"{"kind":"key_down"}"#);
    }

    #[test]
    fn mouse_buttons_map() {
        let mut s = InputState::new();
        let t = Instant::now();
        assert_eq!(
            s.handle(&EventType::ButtonPress(Button::Left), t),
            Some(InputEvent::MouseDown { button: MouseButton::Left })
        );
        assert_eq!(
            s.handle(&EventType::ButtonRelease(Button::Right), t),
            Some(InputEvent::MouseUp { button: MouseButton::Right })
        );
    }

    #[test]
    fn mouse_moves_are_throttled_and_accumulated() {
        let mut s = InputState::new();
        let t0 = Instant::now();
        // first move only establishes the reference position
        assert_eq!(s.handle(&EventType::MouseMove { x: 10.0, y: 10.0 }, t0), None);
        assert_eq!(
            s.handle(&EventType::MouseMove { x: 15.0, y: 10.0 }, t0),
            Some(InputEvent::MouseMove { dx: 5.0, dy: 0.0 })
        );
        // within the throttle window: accumulate, don't emit
        assert_eq!(s.handle(&EventType::MouseMove { x: 17.0, y: 12.0 }, t0), None);
        let later = t0 + Duration::from_millis(20);
        assert_eq!(
            s.handle(&EventType::MouseMove { x: 18.0, y: 12.0 }, later),
            Some(InputEvent::MouseMove { dx: 3.0, dy: 2.0 })
        );
    }
}
