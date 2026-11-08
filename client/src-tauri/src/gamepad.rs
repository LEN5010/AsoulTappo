//! Game controller presses (Windows, XInput).
//!
//! XInput is polled, so it keeps working while a fullscreen game has focus and
//! the desk overlay never does. Like the keyboard hook, nothing about *which*
//! button was pressed leaves this module: every press becomes a plain key-down
//! for the pet, every release a key-up.

use std::sync::atomic::{AtomicU32, Ordering};

use crate::input::InputEvent;

/// Presses since the last `take_presses`, for the log's per-minute summary.
static PRESSES: AtomicU32 = AtomicU32::new(0);

/// Controller presses since the last call.
pub fn take_presses() -> u32 {
    PRESSES.swap(0, Ordering::Relaxed)
}

/// Trigger travel (0-255) past which a trigger counts as pressed.
const TRIGGER_THRESHOLD: u8 = 64;
/// Trigger bits, above XInput's 16 button bits.
const LEFT_TRIGGER: u32 = 1 << 16;
const RIGHT_TRIGGER: u32 = 1 << 17;

/// Buttons and triggers of one controller as a bit set.
pub fn pressed_bits(buttons: u16, left_trigger: u8, right_trigger: u8) -> u32 {
    let mut bits = buttons as u32;
    if left_trigger > TRIGGER_THRESHOLD {
        bits |= LEFT_TRIGGER;
    }
    if right_trigger > TRIGGER_THRESHOLD {
        bits |= RIGHT_TRIGGER;
    }
    bits
}

/// Key-downs for newly pressed bits, then key-ups for released ones.
pub fn diff(before: u32, now: u32, out: &mut Vec<InputEvent>) {
    for _ in 0..(now & !before).count_ones() {
        out.push(InputEvent::KeyDown);
    }
    for _ in 0..(before & !now).count_ones() {
        out.push(InputEvent::KeyUp);
    }
}

#[cfg(target_os = "windows")]
pub fn spawn_poller<F>(emit: F)
where
    F: Fn(InputEvent) + Send + 'static,
{
    use std::time::{Duration, Instant};
    use windows_sys::Win32::UI::Input::XboxController::{XInputGetState, XINPUT_STATE};

    const SLOTS: usize = 4;
    const POLL: Duration = Duration::from_millis(10);
    /// Asking an empty slot is slow, so empty slots are only rechecked this often.
    const RESCAN: Duration = Duration::from_secs(2);
    const ERROR_SUCCESS: u32 = 0;

    std::thread::spawn(move || {
        let mut last = [0u32; SLOTS];
        let mut connected = [false; SLOTS];
        let mut last_scan: Option<Instant> = None;
        let mut out = Vec::new();
        loop {
            let rescan = last_scan.map_or(true, |t| t.elapsed() >= RESCAN);
            if rescan {
                last_scan = Some(Instant::now());
            }
            for slot in 0..SLOTS {
                if !connected[slot] && !rescan {
                    continue;
                }
                let mut state: XINPUT_STATE = unsafe { std::mem::zeroed() };
                let ok = unsafe { XInputGetState(slot as u32, &mut state) } == ERROR_SUCCESS;
                let now = if ok {
                    let pad = state.Gamepad;
                    pressed_bits(pad.wButtons as u16, pad.bLeftTrigger, pad.bRightTrigger)
                } else {
                    0
                };
                if connected[slot] != ok {
                    applog!("pad", "controller {slot} {}", if ok { "connected" } else { "disconnected" });
                }
                connected[slot] = ok;
                PRESSES.fetch_add((now & !last[slot]).count_ones(), Ordering::Relaxed);
                diff(last[slot], now, &mut out);
                last[slot] = now;
            }
            for ev in out.drain(..) {
                emit(ev);
            }
            let any = connected.iter().any(|c| *c);
            std::thread::sleep(if any { POLL } else { RESCAN });
        }
    });
}

/// Controllers are only read on Windows for now.
#[cfg(not(target_os = "windows"))]
pub fn spawn_poller<F>(_emit: F)
where
    F: Fn(InputEvent) + Send + 'static,
{
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn presses_and_releases_become_key_events() {
        let mut out = Vec::new();
        diff(0, 0b101, &mut out);
        assert_eq!(out, vec![InputEvent::KeyDown, InputEvent::KeyDown]);
        out.clear();
        diff(0b101, 0b100, &mut out);
        assert_eq!(out, vec![InputEvent::KeyUp]);
        out.clear();
        diff(0b100, 0b100, &mut out);
        assert!(out.is_empty());
    }

    #[test]
    fn triggers_count_past_the_threshold() {
        assert_eq!(pressed_bits(0, 10, 10), 0);
        assert_eq!(pressed_bits(0, 200, 0), LEFT_TRIGGER);
        assert_eq!(pressed_bits(1, 0, 255), 1 | RIGHT_TRIGGER);
    }

    #[test]
    fn a_disconnect_releases_everything_held() {
        let mut out = Vec::new();
        diff(0b11 | LEFT_TRIGGER, 0, &mut out);
        assert_eq!(out, vec![InputEvent::KeyUp; 3]);
    }
}
