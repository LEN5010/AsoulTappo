//! Gamepad buttons, counted like keys.
//!
//! PRIVACY: same rule as `input`: only "a button went down/up", never which button.
//! Windows uses the XInput backend (gilrs built without `wgi`): XInput is polled and keeps
//! reporting while a full-screen game has focus; Windows.Gaming.Input may not.
use std::time::Duration;

use gilrs::{EventType, Gilrs};

use crate::input::InputEvent;

const POLL: Duration = Duration::from_millis(8);
/// Retry interval when no gamepad backend is available (driver missing, sandbox).
const RETRY: Duration = Duration::from_secs(30);

/// Down/up for button changes only; sticks, triggers moving and connections are ignored.
pub fn map(event: &EventType) -> Option<InputEvent> {
    match event {
        EventType::ButtonPressed(..) => Some(InputEvent::KeyDown),
        EventType::ButtonReleased(..) => Some(InputEvent::KeyUp),
        _ => None,
    }
}

pub fn spawn_gamepad<F>(emit: F)
where
    F: Fn(InputEvent) + Send + 'static,
{
    std::thread::spawn(move || loop {
        let mut gilrs = match Gilrs::new() {
            Ok(g) => g,
            Err(e) => {
                eprintln!("gamepad input unavailable: {e}");
                std::thread::sleep(RETRY);
                continue;
            }
        };
        loop {
            while let Some(ev) = gilrs.next_event() {
                if let Some(out) = map(&ev.event) {
                    emit(out);
                }
            }
            std::thread::sleep(POLL);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn non_button_events_do_not_count() {
        // gilrs exposes no public constructor for button codes, so presses are covered on device.
        assert_eq!(map(&EventType::Connected), None);
        assert_eq!(map(&EventType::Disconnected), None);
        assert_eq!(map(&EventType::Dropped), None);
    }
}
