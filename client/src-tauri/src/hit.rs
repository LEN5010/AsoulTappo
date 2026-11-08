//! Which parts of the desk overlay take the mouse.
//!
//! The overlay window covers the monitor's work area. The frontend reports the
//! rectangles where something is drawn (pets, counter bars, bubbles); outside of
//! them the window ignores the cursor so clicks reach the windows below.

use serde::Deserialize;

/// A rectangle in CSS pixels relative to the overlay's client area.
#[derive(Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct HitRect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

#[derive(Default, Debug)]
pub struct HitState {
    pub rects: Vec<HitRect>,
    /// Something is being dragged: keep taking the mouse until it is dropped.
    pub dragging: bool,
    /// User setting: never take the mouse.
    pub click_through: bool,
    /// The page's device pixel ratio, sent with the rects. On Windows the webview
    /// multiplies the monitor scale by the system text size, so this can differ
    /// from the window scale factor.
    pub page_scale: Option<f64>,
}

impl HitState {
    /// Whether the overlay should take the mouse with the cursor at `cursor`
    /// (physical px, desktop coordinates), given the client area origin
    /// (physical px, desktop coordinates) and the window scale factor, which is
    /// only used until the page has reported its own scale.
    pub fn interactive(&self, cursor: (f64, f64), origin: (f64, f64), window_scale: f64) -> bool {
        if self.click_through {
            return false;
        }
        if self.dragging {
            return true;
        }
        let scale = self.page_scale.unwrap_or(window_scale);
        let scale = if scale > 0.0 { scale } else { 1.0 };
        let x = (cursor.0 - origin.0) / scale;
        let y = (cursor.1 - origin.1) / scale;
        self.rects
            .iter()
            .any(|r| x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn state(rects: Vec<HitRect>) -> HitState {
        HitState { rects, ..Default::default() }
    }

    #[test]
    fn cursor_inside_a_rect_takes_the_mouse() {
        let s = state(vec![HitRect { x: 100.0, y: 50.0, w: 20.0, h: 10.0 }]);
        assert!(s.interactive((105.0, 55.0), (0.0, 0.0), 1.0));
        assert!(!s.interactive((99.0, 55.0), (0.0, 0.0), 1.0));
        assert!(!s.interactive((120.0, 55.0), (0.0, 0.0), 1.0));
    }

    #[test]
    fn converts_physical_desktop_coordinates_to_css_pixels() {
        let s = state(vec![HitRect { x: 100.0, y: 50.0, w: 20.0, h: 10.0 }]);
        // window client area at (1920, 40) on a 150% monitor: css (110, 55) -> physical (2085, 122.5)
        assert!(s.interactive((2085.0, 122.5), (1920.0, 40.0), 1.5));
        assert!(!s.interactive((110.0, 55.0), (1920.0, 40.0), 1.5));
    }

    #[test]
    fn page_scale_replaces_the_window_scale() {
        // 100% monitor with 125% Windows text size: the page draws css (100, 50) at physical (125, 62.5)
        let mut s = state(vec![HitRect { x: 100.0, y: 50.0, w: 20.0, h: 10.0 }]);
        assert!(!s.interactive((130.0, 65.0), (0.0, 0.0), 1.0));
        s.page_scale = Some(1.25);
        assert!(s.interactive((130.0, 65.0), (0.0, 0.0), 1.0));
        assert!(!s.interactive((105.0, 55.0), (0.0, 0.0), 1.0));
    }

    #[test]
    fn dragging_and_click_through_override_the_rects() {
        let mut s = state(vec![]);
        assert!(!s.interactive((1.0, 1.0), (0.0, 0.0), 1.0));
        s.dragging = true;
        assert!(s.interactive((1.0, 1.0), (0.0, 0.0), 1.0));
        s.click_through = true;
        assert!(!s.interactive((1.0, 1.0), (0.0, 0.0), 1.0));
    }
}
