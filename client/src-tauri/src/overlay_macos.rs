//! The overlay uses AppKit points throughout placement and refitting. Tao converts
//! physical positions with the window's current scale, which changes across screens.
//! Screen selection and counting both use NSScreen::screens, whose first entry is
//! the system primary screen. AppKit window access runs on the main thread; high-rate
//! hit-test cursor reads use thread-safe CoreGraphics with cached window geometry.

use std::ffi::c_void;

use objc2::MainThreadMarker;
use objc2_app_kit::{NSScreen, NSWindow};
use objc2_foundation::{NSPoint, NSRect};
use tauri::{PhysicalPosition, WebviewWindow};

/// CoreGraphics global display point (origin at the primary screen's top-left, +Y downward).
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CgPoint {
    pub x: f64,
    pub y: f64,
}

/// Cached AppKit window geometry needed to turn a CoreGraphics cursor point into content-area physical pixels
/// without hopping to the main thread.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Geometry {
    pub content_origin_x: f64,
    pub content_origin_y: f64,
    pub content_height: f64,
    pub primary_height: f64,
    pub scale: f64,
}

#[link(name = "CoreGraphics", kind = "framework")]
extern "C" {
    fn CGEventCreate(source: *const c_void) -> *mut c_void;
    fn CGEventGetLocation(event: *const c_void) -> CgPoint;
    fn CGWindowListCopyWindowInfo(option: u32, relative_to_window: u32) -> *const c_void;
    static kCGWindowIsOnscreen: *const c_void;
}

#[link(name = "CoreFoundation", kind = "framework")]
extern "C" {
    fn CFRelease(cf: *const c_void);
    fn CFArrayGetCount(array: *const c_void) -> isize;
    fn CFArrayGetValueAtIndex(array: *const c_void, idx: isize) -> *const c_void;
    fn CFDictionaryGetValue(dict: *const c_void, key: *const c_void) -> *const c_void;
    fn CFBooleanGetValue(boolean: *const c_void) -> u8;
}

/// Runs `action` with the window's NSWindow on the main thread: at once when called there, otherwise sent there and
/// waited for. AppKit stops the app on some window calls made from another thread.
pub(crate) fn with_window<T: Send + 'static>(
    window: &WebviewWindow,
    action: impl FnOnce(&NSWindow, MainThreadMarker) -> T + Send + 'static,
) -> tauri::Result<T> {
    let owned = window.clone();
    let run = move |mtm| {
        let ptr = owned.ns_window()?;
        // SAFETY: Tauri owns this live NSWindow. Both paths execute on the main thread,
        // and the cloned WebviewWindow remains alive through the action.
        let ns = unsafe { (ptr as *const NSWindow).as_ref() }.ok_or(tauri::Error::InvalidWindowHandle)?;
        Ok(action(ns, mtm))
    };
    if let Some(mtm) = MainThreadMarker::new() {
        return run(mtm);
    }
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    window.run_on_main_thread(move || {
        let mtm = MainThreadMarker::new().expect("Tauri main thread");
        let _ = tx.send(run(mtm));
    })?;
    rx.recv().map_err(|_| tauri::Error::FailedToReceiveMessage)?
}

pub fn primary_index(_window: &WebviewWindow) -> usize {
    0
}

pub fn monitor_count(window: &WebviewWindow) -> tauri::Result<usize> {
    with_window(window, |_, mtm| NSScreen::screens(mtm).len())
}

/// Each screen's key (monitor_pref::key) in NSScreen::screens order, the order `fit_to_monitor` indexes.
pub fn monitor_keys(window: &WebviewWindow) -> tauri::Result<Vec<String>> {
    with_window(window, |_, mtm| {
        NSScreen::screens(mtm)
            .iter()
            .map(|screen| {
                let origin = screen.frame().origin;
                crate::monitor_pref::key(&screen.localizedName().to_string(), origin.x, origin.y)
            })
            .collect()
    })
}

fn rect_text(rect: NSRect) -> String {
    format!(
        "{}x{}+{}+{} pt",
        rect.size.width, rect.size.height, rect.origin.x, rect.origin.y
    )
}

pub fn window_rect(window: &WebviewWindow) -> String {
    with_window(window, |ns, _| rect_text(ns.frame())).unwrap_or_else(|_| "unknown".into())
}

pub fn fit_to_monitor(window: &WebviewWindow, index: usize) -> tauri::Result<Option<String>> {
    with_window(window, move |ns, mtm| {
        let screens = NSScreen::screens(mtm);
        let screen = screens.iter().nth(index).or_else(|| screens.firstObject())?;
        let target = screen.visibleFrame();
        // Set origin and size together in the same coordinate system as visibleFrame.
        // This also produces the resize/backing-scale notifications for the webview.
        ns.setFrame_display(target, true);
        Some(format!(
            "{} at scale {}, screen {}, screen frame {}, window {} at scale {}",
            rect_text(target),
            screen.backingScaleFactor(),
            screen.localizedName(),
            rect_text(screen.frame()),
            rect_text(ns.frame()),
            ns.backingScaleFactor(),
        ))
    })
}

fn same_frame(actual: NSRect, target: NSRect) -> bool {
    // Half a point covers AppKit's pixel rounding on both 1x and 2x displays.
    (actual.origin.x - target.origin.x).abs() <= 0.5
        && (actual.origin.y - target.origin.y).abs() <= 0.5
        && (actual.size.width - target.size.width).abs() <= 0.5
        && (actual.size.height - target.size.height).abs() <= 0.5
}

fn geometry_of(ns: &NSWindow, mtm: MainThreadMarker) -> Geometry {
    let content = ns.contentRectForFrameRect(ns.frame());
    let primary_height = NSScreen::screens(mtm)
        .firstObject()
        .map(|s| s.frame().size.height)
        .unwrap_or(content.origin.y + content.size.height);
    Geometry {
        content_origin_x: content.origin.x,
        content_origin_y: content.origin.y,
        content_height: content.size.height,
        primary_height,
        scale: ns.backingScaleFactor(),
    }
}

/// Reads the window's content geometry, primary screen height, backing scale, and Quartz window number on the main thread.
pub fn read_geometry(window: &WebviewWindow) -> tauri::Result<(Geometry, u32)> {
    with_window(window, |ns, mtm| {
        let num = u32::try_from(ns.windowNumber()).unwrap_or(0);
        (geometry_of(ns, mtm), num)
    })
}

/// Checks refit, actual AppKit visibility, and refreshed geometry in a single main-thread hop.
pub fn check_refit(window: &WebviewWindow, index: usize) -> Option<(bool, bool, Geometry, u32)> {
    with_window(window, move |ns, mtm| {
        let visible = ns.isVisible();
        let screens = NSScreen::screens(mtm);
        let needs = screens
            .iter()
            .nth(index)
            .or_else(|| screens.firstObject())
            .is_some_and(|screen| !same_frame(ns.frame(), screen.visibleFrame()));
        let num = u32::try_from(ns.windowNumber()).unwrap_or(0);
        (visible, needs, geometry_of(ns, mtm), num)
    })
    .ok()
}

/// Reads the global cursor location in CoreGraphics display coordinates from any thread.
fn cg_cursor() -> Option<CgPoint> {
    // SAFETY: CGEventCreate(NULL) is thread-safe and creates a dummy event populated with the current cursor location.
    unsafe {
        let event = CGEventCreate(std::ptr::null());
        if event.is_null() {
            return None;
        }
        let point = CGEventGetLocation(event);
        CFRelease(event);
        Some(point)
    }
}

/// Converts a CoreGraphics global display point (primary screen top-left origin, +Y down) into
/// content-area physical pixels using the window's cached AppKit geometry (primary screen bottom-left origin, +Y up).
fn cg_to_content_cursor(point: CgPoint, g: Geometry) -> PhysicalPosition<f64> {
    let local = NSPoint::new(point.x - g.content_origin_x, g.primary_height - point.y - g.content_origin_y);
    content_cursor(local, g.content_height, g.scale)
}

/// Thread-safe hit-test cursor lookup using cached window geometry (no main-thread dispatch).
pub fn hit_cursor_cached(geometry: Geometry) -> Option<PhysicalPosition<f64>> {
    cg_cursor().map(|pt| cg_to_content_cursor(pt, geometry))
}

/// Thread-safe check of whether `window_number` is currently ordered onscreen (used while hidden to spot hotkey show).
pub fn window_onscreen(window_number: u32) -> Option<bool> {
    const K_CG_WINDOW_LIST_OPTION_INCLUDING_WINDOW: u32 = 1 << 3;
    if window_number == 0 {
        return None;
    }
    // SAFETY: CoreGraphics/CoreFoundation calls on a single window ID; the returned CFArray is released before return.
    unsafe {
        let list = CGWindowListCopyWindowInfo(K_CG_WINDOW_LIST_OPTION_INCLUDING_WINDOW, window_number);
        if list.is_null() {
            return None;
        }
        let onscreen = if CFArrayGetCount(list) > 0 {
            let dict = CFArrayGetValueAtIndex(list, 0);
            if dict.is_null() {
                false
            } else {
                let val = CFDictionaryGetValue(dict, kCGWindowIsOnscreen);
                !val.is_null() && CFBooleanGetValue(val) != 0
            }
        } else {
            false
        };
        CFRelease(list);
        Some(onscreen)
    }
}

fn content_cursor(point: NSPoint, height: f64, scale: f64) -> PhysicalPosition<f64> {
    PhysicalPosition::new(point.x * scale, (height - point.y) * scale)
}

#[cfg(test)]
mod tests {
    use super::*;
    use objc2_foundation::NSSize;

    fn rect(x: f64, y: f64, w: f64, h: f64) -> NSRect {
        NSRect::new(NSPoint::new(x, y), NSSize::new(w, h))
    }

    #[test]
    fn refit_compares_appkit_points_with_pixel_rounding_tolerance() {
        let target = rect(1512.0, -200.0, 1920.0, 1055.0);
        assert!(same_frame(target, target));
        assert!(same_frame(rect(1512.0, -200.0, 1920.0, 1055.5), target));
        assert!(!same_frame(rect(1512.0, 120.0, 1920.0, 1056.0), target));
        assert!(!same_frame(rect(756.0, -100.0, 960.0, 527.5), target));
        assert!(!same_frame(rect(1512.0, -200.0, 1920.0, 1000.0), target));
    }

    #[test]
    fn refit_handles_screens_left_of_and_above_the_primary() {
        for target in [rect(-1920.0, 400.0, 1920.0, 1055.0), rect(0.0, 982.0, 1512.0, 944.0)] {
            assert!(same_frame(target, target));
            assert!(!same_frame(
                rect(0.0, 0.0, target.size.width, target.size.height),
                target
            ));
        }
    }

    #[test]
    fn mouse_coordinates_follow_the_window_scale_and_top_left_origin() {
        let point = NSPoint::new(110.0, 745.0);
        for scale in [1.0, 2.0] {
            let cursor = content_cursor(point, 800.0, scale);
            let state = crate::hit::HitState {
                rects: vec![crate::hit::HitRect {
                    x: 100.0,
                    y: 50.0,
                    w: 20.0,
                    h: 10.0,
                    keep: false,
                }],
                page_scale: Some(scale),
                ..Default::default()
            };
            assert!(state.interactive((cursor.x, cursor.y), (0.0, 0.0), scale));
            let outside = content_cursor(NSPoint::new(99.0, 745.0), 800.0, scale);
            assert!(!state.interactive((outside.x, outside.y), (0.0, 0.0), scale));
        }
    }

    #[test]
    fn negative_pet_coordinates_use_the_scale_of_each_screen() {
        let rect = crate::hit::HitRect { x: -12.0, y: -8.0, w: 20.0, h: 16.0, keep: false };
        // AppKit supplies points relative to the window on either screen.
        for (scale, origin_x, cursor_x, expected) in [
            (2.0, 0.0, -10.0, (-20.0, -8.0)),
            (1.0, -1920.0, -1930.0, (-10.0, -4.0)),
        ] {
            let state = crate::hit::HitState {
                rects: vec![rect],
                page_scale: Some(scale),
                ..Default::default()
            };
            let cursor = content_cursor(NSPoint::new(cursor_x - origin_x, 804.0), 800.0, scale);
            assert_eq!((cursor.x, cursor.y), expected);
            assert!(state.interactive(expected, (0.0, 0.0), scale));
            let edge = content_cursor(NSPoint::new(8.0, 804.0), 800.0, scale);
            assert!(!state.interactive((edge.x, edge.y), (0.0, 0.0), scale));
        }
    }
}
