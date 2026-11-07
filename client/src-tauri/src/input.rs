//! Global keyboard / mouse hook (via `rdev`).
//!
//! PRIVACY: this module never forwards *which* key was pressed. The frontend
//! only learns "a key went down/up", which mouse button, and relative mouse
//! movement (used to animate the local pet; never sent over the network).

use std::collections::HashMap;
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

/// Spawn the blocking hook on a background thread; `emit` is called for every
/// filtered event.
///
/// The OS hook callback only timestamps the event and queues it: Windows silently
/// removes a low-level hook whose callback runs past `LowLevelHooksTimeout`, which
/// a busy fullscreen game easily causes if the callback does IPC itself. Filtering
/// and emitting happen on a separate thread.
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

    std::thread::spawn(move || {
        // rdev otherwise looks up the keyboard layout (TIS/TSM) on this thread for
        // every key, which macOS 14+ only allows on the main thread and aborts on.
        #[cfg(target_os = "macos")]
        rdev::set_is_main_thread(false);

        loop {
            let tx = tx.clone();
            // Coalesce raw mouse moves at the producer: high-polling mice can fire
            // thousands of moves per second, and an unbounded queue would grow if
            // the consumer stalls. Positions are absolute, so skipping intermediate
            // moves loses nothing. Key and button down/up are always queued.
            let mut last_move: Option<Instant> = None;
            let result = rdev::listen(move |event| {
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
            match result {
                // listen only returns on explicit failure (e.g. no accessibility permission on
                // macOS); retry instead of losing input until restart. This does NOT cover
                // Windows silently removing a slow low-level hook: listen never returns then.
                Err(e) => eprintln!("global input hook stopped: {e:?}; retrying"),
                Ok(()) => {}
            }
            std::thread::sleep(Duration::from_secs(5));
        }
    });
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
