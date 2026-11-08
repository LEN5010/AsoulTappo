//! Global keyboard / mouse hook (via `rdev`).
//!
//! PRIVACY: this module never forwards *which* key was pressed. The frontend
//! only learns "a key went down/up", which mouse button, and relative mouse
//! movement (used to animate the local pet; never sent over the network).

use std::collections::HashMap;
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

/// Spawn the global hook and the thread that filters its events; `emit` is called
/// for every filtered event.
///
/// The OS hook callback only timestamps the event and queues it: Windows silently
/// removes a low-level hook whose callback runs past `LowLevelHooksTimeout`, which
/// a busy fullscreen game easily causes if the callback does IPC itself. Filtering
/// and emitting happen on a separate thread.
///
/// Each hook gets a thread of its own that ends when `rdev::listen` returns. rdev
/// never unhooks; the OS removes a thread's hooks when the thread exits, so ending
/// the thread is how a hook is replaced without leaving the old one installed.
pub fn spawn_hook<F>(emit: F)
where
    F: Fn(InputEvent) + Send + 'static,
{
    let (tx, rx) = std::sync::mpsc::channel::<(EventType, Instant)>();

    std::thread::spawn(move || {
        let mut state = InputState::new();
        for (ev, at) in rx {
            if let Some(out) = state.handle(&ev, at) {
                emit(out);
            }
        }
    });

    std::thread::spawn(move || loop {
        let hook = {
            let tx = tx.clone();
            std::thread::spawn(move || run_hook(tx))
        };
        let replaced = watchdog::watch(&hook);
        // The old hook thread must be gone before the next `listen` replaces rdev's global callback.
        let _ = hook.join();
        if !replaced {
            std::thread::sleep(RETRY);
        }
    });
}

/// Install the hook and pump its events until `listen` returns.
fn run_hook(tx: Sender<(EventType, Instant)>) {
    // rdev otherwise looks up the keyboard layout (TIS/TSM) on this thread for
    // every key, which macOS 14+ only allows on the main thread and aborts on.
    #[cfg(target_os = "macos")]
    rdev::set_is_main_thread(false);
    watchdog::enter();

    // Coalesce raw mouse moves at the producer: high-polling mice can fire
    // thousands of moves per second, and an unbounded queue would grow if
    // the consumer stalls. Positions are absolute, so skipping intermediate
    // moves loses nothing. Key and button down/up are always queued.
    let mut last_move: Option<Instant> = None;
    let result = rdev::listen(move |event| {
        watchdog::heard();
        let now = Instant::now();
        match event.event_type {
            EventType::Wheel { .. } => return,
            EventType::MouseMove { .. } => {
                if last_move.is_some_and(|t| now.duration_since(t) < Duration::from_millis(4)) {
                    return;
                }
                last_move = Some(now);
            }
            _ => {}
        }
        let _ = tx.send((event.event_type, now));
    });
    if let Err(e) = result {
        eprintln!("global input hook stopped: {e:?}; retrying");
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
        GetCurrentThread, GetCurrentThreadId, SetThreadPriority, THREAD_PRIORITY_TIME_CRITICAL,
    };
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};
    use windows_sys::Win32::UI::WindowsAndMessaging::{PostThreadMessageW, WM_QUIT};

    const CHECK: Duration = Duration::from_secs(2);
    /// A hook lives at least this long before it may be replaced.
    const MIN_LIFE: Duration = Duration::from_secs(10);

    static HOOK_THREAD: AtomicU32 = AtomicU32::new(0);
    static LAST_HEARD: AtomicU32 = AtomicU32::new(0);

    /// Called on the hook thread before it installs the hook.
    pub fn enter() {
        unsafe {
            HOOK_THREAD.store(GetCurrentThreadId(), Ordering::Release);
            LAST_HEARD.store(GetTickCount(), Ordering::Relaxed);
            // The thread sleeps in GetMessage and its callback only timestamps and queues (plus
            // rdev's key-name lookup), so the top priority costs nothing and keeps a game that
            // saturates the CPU from pushing the callback past the hook timeout.
            SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
        }
    }

    pub fn heard() {
        LAST_HEARD.store(unsafe { GetTickCount() }, Ordering::Relaxed);
    }

    /// Wait for the hook thread to end; returns true when it was ended for going silent.
    pub fn watch(hook: &JoinHandle<()>) -> bool {
        let started = Instant::now();
        while !hook.is_finished() {
            std::thread::sleep(CHECK);
            if started.elapsed() >= MIN_LIFE && missed_input() {
                eprintln!("global input hook went silent; replacing it");
                // WM_QUIT makes rdev's GetMessage return, so `listen` and the thread end.
                // Posting fails until the thread has a message queue: keep trying.
                let id = HOOK_THREAD.load(Ordering::Acquire);
                while !hook.is_finished() {
                    unsafe { PostThreadMessageW(id, WM_QUIT, 0, 0) };
                    std::thread::sleep(Duration::from_millis(100));
                }
                return true;
            }
        }
        false
    }

    fn missed_input() -> bool {
        let mut info = LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };
        if unsafe { GetLastInputInfo(&mut info) } == 0 {
            return false;
        }
        super::went_silent(info.dwTime, LAST_HEARD.load(Ordering::Relaxed))
    }
}

/// Only Windows drops hooks silently; elsewhere this just waits for the hook thread.
#[cfg(not(target_os = "windows"))]
mod watchdog {
    pub fn enter() {}
    pub fn heard() {}
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
