//! The overlay uses AppKit points throughout placement and refitting. Tao converts
//! physical positions with the window's current scale, which changes across screens.
//! Screen selection and counting both use NSScreen::screens, whose first entry is
//! the system primary screen. All AppKit window access runs on the main thread.

use objc2::MainThreadMarker;
use objc2_app_kit::{NSScreen, NSWindow};
use objc2_foundation::{NSPoint, NSRect};
use tauri::{PhysicalPosition, WebviewWindow};

fn with_window<T: Send + 'static>(
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

pub fn needs_refit(window: &WebviewWindow, index: usize) -> bool {
    with_window(window, move |ns, mtm| {
        let screens = NSScreen::screens(mtm);
        screens
            .iter()
            .nth(index)
            .or_else(|| screens.firstObject())
            .is_some_and(|screen| !same_frame(ns.frame(), screen.visibleFrame()))
    })
    .unwrap_or(false)
}

/// Mouse positions are relative to the content area on macOS. This avoids Tao's
/// global cursor coordinates, which use the primary screen's scale factor.
pub fn hit_origin(_window: &WebviewWindow) -> tauri::Result<PhysicalPosition<i32>> {
    Ok(PhysicalPosition::new(0, 0))
}

pub fn hit_cursor(window: &WebviewWindow) -> tauri::Result<PhysicalPosition<f64>> {
    with_window(window, |ns, _| {
        let point = ns.mouseLocationOutsideOfEventStream();
        let content = ns.contentRectForFrameRect(ns.frame());
        content_cursor(point, content.size.height, ns.backingScaleFactor())
    })
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
                }],
                page_scale: Some(scale),
                ..Default::default()
            };
            assert!(state.interactive((cursor.x, cursor.y), (0.0, 0.0), scale));
            let outside = content_cursor(NSPoint::new(99.0, 745.0), 800.0, scale);
            assert!(!state.interactive((outside.x, outside.y), (0.0, 0.0), scale));
        }
    }
}
