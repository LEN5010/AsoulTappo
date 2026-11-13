//! Sony's numbered HID input reports. Packet layouts are described by SDL's
//! HIDAPI PS4/PS5 drivers (src/joystick/hidapi/SDL_hidapi_ps4.c and ps5.c).
//! Only button transitions leave this module. Axes, sensors and packet counters
//! are excluded from the pressed bit set.

use std::collections::HashSet;
use std::ffi::CString;
use std::time::{Duration, Instant};

use hidapi::{HidApi, HidDevice};

use super::{pressed_bits, record_changes, InputEvent};

const POLL: Duration = Duration::from_millis(10);
const RESCAN: Duration = Duration::from_secs(2);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Model {
    DualShock4,
    DualSense,
}

impl Model {
    fn from_id(vendor: u16, product: u16) -> Option<Self> {
        match (vendor, product) {
            (0x054c, 0x05c4 | 0x09cc) => Some(Self::DualShock4),
            (0x054c, 0x0ce6 | 0x0df2) => Some(Self::DualSense),
            _ => None,
        }
    }

    /// Convert USB, simple Bluetooth and enhanced Bluetooth packets to the same
    /// bits. The trigger's digital flag is excluded so it counts once at the
    /// same analog threshold as XInput. PS/touchpad/mute/Edge buttons have their
    /// own bits above the triggers.
    fn pressed(self, report: &[u8]) -> Option<u32> {
        let (offset, buttons_offset, trigger_offset, extra_mask) = match (self, *report.first()?, report.len()) {
            (Self::DualShock4, 0x01, 10 | 64..=128) => (1, 4, 7, 0x03),
            (Self::DualShock4, 0x11..=0x19, 78..=128) if report[1] & 0x80 != 0 => (3, 4, 7, 0x03),
            (Self::DualSense, 0x01, 10 | 78) => (1, 4, 7, 0x03),
            (Self::DualSense, 0x01, 64) => (1, 7, 4, 0xf7),
            (Self::DualSense, 0x31, 78) => (2, 7, 4, 0xf7),
            _ => return None,
        };
        let state = &report[offset..];
        let buttons = &state[buttons_offset..buttons_offset + 3];
        // Clockwise hat positions start at up. Values 8..15 mean released.
        const HAT: [u16; 16] = [1, 3, 2, 6, 4, 12, 8, 9, 0, 0, 0, 0, 0, 0, 0, 0];
        let digital =
            HAT[(buttons[0] & 0x0f) as usize] | u16::from(buttons[0] & 0xf0) | (u16::from(buttons[1] & 0xf3) << 8);
        Some(
            pressed_bits(digital, state[trigger_offset], state[trigger_offset + 1])
                | (u32::from(buttons[2] & extra_mask) << 18),
        )
    }
}

struct Pad {
    path: CString,
    device: HidDevice,
    model: Model,
    held: u32,
}

impl Pad {
    fn poll(&mut self, out: &mut Vec<InputEvent>) -> hidapi::HidResult<()> {
        let mut report = [0u8; 128];
        loop {
            let size = self.device.read_timeout(&mut report, 0)?;
            if size == 0 {
                return Ok(());
            }
            if let Some(now) = self.model.pressed(&report[..size]) {
                record_changes(self.held, now, out);
                self.held = now;
            }
        }
    }

    fn disconnect(&self, out: &mut Vec<InputEvent>) {
        record_changes(self.held, 0, out);
        applog!("pad", "{:?} disconnected", self.model);
    }
}

pub(super) fn spawn_poller<F>(emit: F)
where
    F: Fn(InputEvent) + Send + 'static,
{
    std::thread::spawn(move || {
        let mut api = match HidApi::new() {
            Ok(api) => api,
            Err(e) => {
                applog!("pad", "PlayStation HID initialization failed: {e}");
                return;
            }
        };
        let mut pads: Vec<Pad> = Vec::new();
        // A device may be opened by a game in exclusive mode. Retry it at each
        // scan and log the first failure until it opens or disappears.
        let mut unavailable = HashSet::new();
        let mut scanned: Option<Instant> = None;
        let mut out = Vec::new();
        loop {
            if scanned.is_none_or(|at| at.elapsed() >= RESCAN) {
                scanned = Some(Instant::now());
                match api.refresh_devices() {
                    Ok(()) => {
                        let devices: Vec<_> = api
                            .device_list()
                            .filter_map(|info| {
                                let model = Model::from_id(info.vendor_id(), info.product_id())?;
                                (info.usage_page() == 1 && matches!(info.usage(), 4 | 5)).then_some((info, model))
                            })
                            .collect();
                        pads.retain(|pad| {
                            let connected = devices.iter().any(|(info, _)| info.path() == pad.path.as_c_str());
                            if !connected {
                                pad.disconnect(&mut out);
                            }
                            connected
                        });
                        unavailable
                            .retain(|path: &CString| devices.iter().any(|(info, _)| info.path() == path.as_c_str()));
                        for (info, model) in devices {
                            if pads.iter().any(|pad| pad.path.as_c_str() == info.path()) {
                                continue;
                            }
                            match info.open_device(&api) {
                                Ok(device) => {
                                    unavailable.remove(info.path());
                                    applog!("pad", "{model:?} connected via HID");
                                    pads.push(Pad {
                                        path: info.path().to_owned(),
                                        device,
                                        model,
                                        held: 0,
                                    });
                                }
                                Err(e) => {
                                    if unavailable.insert(info.path().to_owned()) {
                                        applog!("pad", "{model:?} HID open failed: {e}");
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => applog!("pad", "PlayStation HID scan failed: {e}"),
                }
            }
            pads.retain_mut(|pad| match pad.poll(&mut out) {
                Ok(()) => true,
                Err(e) => {
                    applog!("pad", "{:?} HID read ended: {e}", pad.model);
                    pad.disconnect(&mut out);
                    false
                }
            });
            for event in out.drain(..) {
                emit(event);
            }
            std::thread::sleep(if pads.is_empty() { RESCAN } else { POLL });
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::gamepad::{diff, LEFT_TRIGGER, RIGHT_TRIGGER};

    fn simple_report(size: usize, offset: usize) -> Vec<u8> {
        let mut report = vec![0; size];
        report[0] = if offset == 3 { 0x11 } else { 0x01 };
        report[1] = 0x80;
        report[offset + 4] = 0x28; // Cross, hat released.
        report[offset + 5] = 0x11; // L1 and Share/Create.
        report[offset + 6] = 0xfe; // Touchpad plus a changing packet counter.
        report[offset + 7] = 65;
        report[offset + 8] = 64;
        report
    }

    #[test]
    fn sony_product_ids_select_the_report_layout() {
        for id in [0x05c4, 0x09cc] {
            assert_eq!(Model::from_id(0x054c, id), Some(Model::DualShock4));
        }
        for id in [0x0ce6, 0x0df2] {
            assert_eq!(Model::from_id(0x054c, id), Some(Model::DualSense));
        }
        assert_eq!(Model::from_id(0x045e, 0x028e), None);
        assert_eq!(Model::from_id(0x054c, 0x0ba0), None);
    }

    #[test]
    fn dualshock_usb_and_bluetooth_decode_the_same_buttons() {
        let expected = 0x1120 | LEFT_TRIGGER | (2 << 18);
        for (size, offset) in [(10, 1), (64, 1), (128, 1), (78, 3)] {
            assert_eq!(Model::DualShock4.pressed(&simple_report(size, offset)), Some(expected));
        }
    }

    #[test]
    fn dualsense_simple_bluetooth_reports_use_the_dualshock_layout() {
        for size in [10, 78] {
            let report = simple_report(size, 1);
            assert_eq!(Model::DualSense.pressed(&report), Model::DualShock4.pressed(&report));
        }
    }

    #[test]
    fn dualsense_usb_and_enhanced_bluetooth_use_their_own_offsets() {
        for (size, offset, id) in [(64, 1, 0x01), (78, 2, 0x31)] {
            let mut report = vec![0; size];
            report[0] = id;
            report[offset + 4] = 65;
            report[offset + 5] = 255;
            report[offset + 6] = 0xff; // Packet counter, excluded.
            report[offset + 7] = 0x88; // Triangle, hat released.
            report[offset + 8] = 0xcc; // L3/R3 and digital trigger flags.
            report[offset + 9] = 0xff; // PS, touchpad, mute and Edge buttons.
            assert_eq!(
                Model::DualSense.pressed(&report),
                Some(0xc080 | LEFT_TRIGGER | RIGHT_TRIGGER | (0xf7 << 18))
            );
        }
    }

    #[test]
    fn hat_diagonals_have_two_buttons_and_reserved_values_are_released() {
        let mut report = vec![0; 10];
        report[0] = 1;
        for (hat, expected) in [1, 3, 2, 6, 4, 12, 8, 9, 0, 0, 0, 0, 0, 0, 0, 0]
            .into_iter()
            .enumerate()
        {
            report[5] = hat as u8;
            assert_eq!(Model::DualShock4.pressed(&report), Some(expected));
        }
    }

    #[test]
    fn axes_counters_and_subthreshold_triggers_do_not_count() {
        let mut report = vec![0xff; 10];
        report[0] = 1;
        report[5] = 8;
        report[6] = 0x0c; // Digital trigger flags must not count separately.
        report[7] = 0xfc;
        report[8] = 64;
        report[9] = 64;
        assert_eq!(Model::DualShock4.pressed(&report), Some(0));
        report[8] = 65;
        assert_eq!(Model::DualShock4.pressed(&report), Some(LEFT_TRIGGER));
    }

    #[test]
    fn repeated_reports_and_disconnect_preserve_press_release_balance() {
        let report = simple_report(64, 1);
        let now = Model::DualShock4.pressed(&report).unwrap();
        let mut out = Vec::new();
        diff(0, now, &mut out);
        assert_eq!(out, vec![InputEvent::KeyDown; 5]);
        out.clear();
        diff(now, Model::DualShock4.pressed(&report).unwrap(), &mut out);
        assert!(out.is_empty());
        diff(now, 0, &mut out);
        assert_eq!(out, vec![InputEvent::KeyUp; 5]);
    }

    #[test]
    fn switching_dualsense_report_modes_preserves_held_buttons() {
        let simple = Model::DualSense.pressed(&simple_report(10, 1)).unwrap();
        let mut enhanced = vec![0; 78];
        enhanced[0] = 0x31;
        enhanced[6] = 65;
        enhanced[7] = 64;
        enhanced[9] = 0x28;
        enhanced[10] = 0x11;
        enhanced[11] = 0x02;
        let mut out = Vec::new();
        diff(simple, Model::DualSense.pressed(&enhanced).unwrap(), &mut out);
        assert!(out.is_empty());
    }

    #[test]
    fn incomplete_and_non_input_reports_are_ignored() {
        for model in [Model::DualShock4, Model::DualSense] {
            for size in 0..10 {
                assert_eq!(model.pressed(&vec![1; size]), None);
            }
            assert_eq!(model.pressed(&[0x05; 64]), None);
            assert_eq!(model.pressed(&[0x31; 77]), None);
        }
        assert_eq!(Model::DualShock4.pressed(&[0x11; 78]), None);
    }
}
