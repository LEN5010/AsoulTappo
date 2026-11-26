//! Where the panel window goes the first time it is shown: centred on the pet's monitor unless that covers what the
//! desk draws there (the pet, its bar, its bubbles), else the nearest spot that does not; when no spot clears it, the
//! one that covers the least. All values are in one monitor's own pixels.

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

impl Rect {
    fn right(&self) -> f64 {
        self.x + self.w
    }

    fn bottom(&self) -> f64 {
        self.y + self.h
    }

    fn grown(&self, by: f64) -> Rect {
        Rect { x: self.x - by, y: self.y - by, w: self.w + 2.0 * by, h: self.h + 2.0 * by }
    }

    /// The area two rectangles share.
    pub fn overlap(&self, other: &Rect) -> f64 {
        let w = self.right().min(other.right()) - self.x.max(other.x);
        let h = self.bottom().min(other.bottom()) - self.y.max(other.y);
        if w > 0.0 && h > 0.0 {
            w * h
        } else {
            0.0
        }
    }
}

/// The panel's page in CSS px: the window is this size times the page's zoom, in logical pixels.
pub const PAGE: (f64, f64) = (1000.0, 720.0);
/// The sizes a player can pick (`panelScale`, src/stores/settings.ts).
pub const SCALES: (f64, f64) = (0.9, 1.5);
/// What the window keeps clear of the work area's sides, in total, in the monitor's pixels.
const ROOM: f64 = 20.0;

/// The panel on a monitor whose work area is `area_w`×`area_h` of its pixels, `scale` of them to a logical pixel, at
/// the size the player picked: the window's width and height in the monitor's pixels, and the page's zoom.
///
/// The window keeps the page's proportions, so the page is laid out at `PAGE` and drawn `zoom` times as large. A pick
/// that does not fit comes down until it does, but not below the pick itself or 1: from there the window is cut to the
/// work area and the page lays itself out in what is left (its container queries), as it did before the setting.
pub fn fit(area_w: f64, area_h: f64, scale: f64, picked: f64) -> (f64, f64, f64) {
    let picked = if picked.is_finite() { picked.clamp(SCALES.0, SCALES.1) } else { 1.0 };
    let room = ((area_w - ROOM) / (PAGE.0 * scale)).min((area_h - ROOM) / (PAGE.1 * scale));
    let zoom = picked.min(room).max(picked.min(1.0));
    ((PAGE.0 * zoom * scale).min(area_w - ROOM), (PAGE.1 * zoom * scale).min(area_h - ROOM), zoom)
}

/// The size the page is drawn at: the player's pick where the web view can zoom its page, else the page's own size
/// (macOS before 11 has no page zoom).
pub fn usable_pick(picked: f64, can_zoom: bool) -> f64 {
    if can_zoom {
        picked
    } else {
        1.0
    }
}

/// The panel at `at` sized again for the work area `area` (`fit`): its new window and the page's zoom. Its centre
/// stays where it was, held inside the work area.
pub fn refit(area: Rect, scale: f64, picked: f64, at: Rect) -> (Rect, f64) {
    let (w, h, zoom) = fit(area.w, area.h, scale, picked);
    let (cx, cy) = (at.x + at.w / 2.0, at.y + at.h / 2.0);
    let x = (cx - w / 2.0).clamp(area.x, (area.right() - w).max(area.x));
    let y = (cy - h / 2.0).clamp(area.y, (area.bottom() - h).max(area.y));
    (Rect { x, y, w, h }, zoom)
}

/// The work area the panel was last fitted to, in its monitor's pixels, and that monitor's scale.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Home {
    pub area: Rect,
    pub scale: f64,
}

/// Whether a panel fitted to `home` and now on `now` needs fitting again: it went to another monitor, or its own
/// monitor's work area or scale changed. A panel never fitted is left to its first show.
pub fn left_home(home: Option<Home>, now: Home) -> bool {
    home.is_some_and(|home| home != now)
}

/// How much of `avoid` a window at `spot` covers.
pub fn covered(spot: &Rect, avoid: &[Rect]) -> f64 {
    avoid.iter().map(|r| spot.overlap(r)).sum()
}

/// Top left corner for a `w`×`h` window in `area`, kept `edge` from its sides when there is room, and `gap` from each
/// rectangle in `avoid`. Among the spots that cover the least of `avoid` (with its gap), the one nearest the centre of
/// `area`.
pub fn place(area: Rect, w: f64, h: f64, avoid: &[Rect], gap: f64, edge: f64) -> (f64, f64) {
    let span = |start: f64, room: f64, size: f64| {
        let slack = (room - size).max(0.0);
        let margin = edge.min(slack / 2.0);
        (start + margin, start + slack - margin)
    };
    let (left, right) = span(area.x, area.w, w);
    let (top, bottom) = span(area.y, area.h, h);
    let want = (area.x + (area.w - w) / 2.0, area.y + (area.h - h) / 2.0);
    let avoid: Vec<Rect> = avoid.iter().map(|r| r.grown(gap)).collect();

    let mut xs = vec![want.0, left, right];
    let mut ys = vec![want.1, top, bottom];
    for r in &avoid {
        xs.extend([r.x - w, r.right()]);
        ys.extend([r.y - h, r.bottom()]);
    }
    let xs: Vec<f64> = xs.into_iter().map(|x| x.clamp(left, right)).collect();
    let ys: Vec<f64> = ys.into_iter().map(|y| y.clamp(top, bottom)).collect();

    let mut best = (f64::INFINITY, f64::INFINITY, want);
    for &x in &xs {
        for &y in &ys {
            // Whole pixels, so rounding never decides between two spots.
            let cover = covered(&Rect { x, y, w, h }, &avoid).round();
            let off = (x - want.0).abs() + (y - want.1).abs();
            if cover < best.0 || (cover == best.0 && off < best.1) {
                best = (cover, off, (x, y));
            }
        }
    }
    best.2
}

#[cfg(test)]
mod tests {
    use super::*;

    const GAP: f64 = 16.0;
    const EDGE: f64 = 10.0;

    fn area(x: f64, y: f64, w: f64, h: f64) -> Rect {
        Rect { x, y, w, h }
    }

    /// The default pet spot (src/stores/desk.ts, defaultPetPos): 48 from the right, 80 from the bottom.
    fn pet(a: Rect, scale: f64) -> Rect {
        let (w, h) = (180.0 * scale, 240.0 * scale);
        Rect { x: a.right() - w - 48.0 * scale, y: a.bottom() - h - 80.0 * scale, w, h }
    }

    /// The panel's size on a monitor at the default size.
    fn size(a: Rect, scale: f64) -> (f64, f64) {
        let (w, h, _) = fit(a.w, a.h, scale, 1.0);
        (w, h)
    }

    fn close(a: f64, b: f64) -> bool {
        (a - b).abs() < 1e-6
    }

    #[test]
    fn the_default_size_is_the_old_one_everywhere() {
        // Work areas in their own pixels and their scale: big, tall and short ones.
        for (w, h, scale) in [
            (1920.0, 1032.0, 1.0),
            (1366.0, 708.0, 1.25),
            (1280.0, 672.0, 1.0),
            (1920.0, 1008.0, 1.5),
            (2560.0, 1410.0, 2.0),
            (800.0, 560.0, 1.0),
        ] {
            let (fw, fh, zoom) = fit(w, h, scale, 1.0);
            assert_eq!(zoom, 1.0);
            assert_eq!((fw, fh), ((1000.0 * scale).min(w - 20.0), (720.0 * scale).min(h - 20.0)));
        }
    }

    #[test]
    fn a_bigger_pick_keeps_the_proportions() {
        // 2560×1440 at 100%, 40 for the taskbar.
        let (w, h, zoom) = fit(2560.0, 1400.0, 1.0, 1.5);
        assert_eq!(zoom, 1.5);
        assert_eq!((w, h), (1500.0, 1080.0));
        // An ultrawide one: room for nearly ×1.9, the pick is the most it gets.
        assert_eq!(fit(3440.0, 1392.0, 1.0, 1.5).2, 1.5);
    }

    #[test]
    fn a_pick_that_does_not_fit_comes_down_to_what_does() {
        // 1920×1080 at 100% with a 48 px taskbar: ×1.5 does not fit, the window takes the work area's height.
        let (w, h, zoom) = fit(1920.0, 1032.0, 1.0, 1.5);
        assert!(close(zoom, 1012.0 / 720.0));
        assert!(close(h, 1012.0));
        assert!(close(w / h, 1000.0 / 720.0));
        // A MacBook at 200% (1280×800 points, menu bar and Dock out): the height lets ×1 at most, and no less.
        let (w, h, zoom) = fit(2560.0, 1410.0, 2.0, 1.3);
        assert_eq!(zoom, 1.0);
        assert_eq!((w, h), (2000.0, 1390.0));
        // A portrait monitor: the width is what limits it.
        let (w, _, zoom) = fit(1080.0, 1872.0, 1.0, 1.5);
        assert!(close(zoom, 1.06));
        assert!(close(w, 1060.0));
    }

    #[test]
    fn a_smaller_pick_fits_a_small_screen_whole() {
        // 1280×720 at 100% (or 1920×1080 at 150%): ×0.9 shows the whole page, the default cuts its height.
        let (w, h, zoom) = fit(1280.0, 672.0, 1.0, 0.9);
        assert_eq!(zoom, 0.9);
        assert!(close(w, 900.0) && close(h, 648.0));
        let (w, h, zoom) = fit(1920.0, 1008.0, 1.5, 0.9);
        assert_eq!(zoom, 0.9);
        assert!(close(w, 1350.0) && close(h, 972.0));
        // 1366×768 at 125%: even ×0.9 is cut a little, never below the pick.
        let (w, h, zoom) = fit(1366.0, 708.0, 1.25, 0.9);
        assert_eq!(zoom, 0.9);
        assert!(close(w, 1125.0));
        assert_eq!(h, 688.0);
    }

    #[test]
    fn a_pick_out_of_range_is_held_to_it() {
        assert_eq!(fit(3840.0, 2100.0, 1.0, 9.0).2, SCALES.1);
        assert_eq!(fit(3840.0, 2100.0, 1.0, 0.1).2, SCALES.0);
        assert_eq!(fit(3840.0, 2100.0, 1.0, f64::NAN).2, 1.0);
    }

    fn inside(a: Rect, x: f64, y: f64, w: f64, h: f64) -> bool {
        x >= a.x && y >= a.y && x + w <= a.right() && y + h <= a.bottom()
    }

    #[test]
    fn a_web_view_without_page_zoom_keeps_the_page_at_its_own_size() {
        assert_eq!(usable_pick(1.5, true), 1.5);
        assert_eq!(usable_pick(0.9, true), 0.9);
        assert_eq!(usable_pick(1.5, false), 1.0);
        assert_eq!(usable_pick(0.9, false), 1.0);
        assert_eq!(fit(2560.0, 1400.0, 1.0, usable_pick(1.5, false)), (1000.0, 720.0, 1.0));
    }

    #[test]
    fn moved_to_a_smaller_work_area_the_panel_is_fitted_to_it() {
        // ×1.5 on a 2560×1440 monitor at 100%, then dragged onto a 1920×1080 one at 150% to its right.
        let big = area(0.0, 0.0, 2560.0, 1400.0);
        let (w, h, zoom) = fit(big.w, big.h, 1.0, 1.5);
        assert_eq!((w, h, zoom), (1500.0, 1080.0, 1.5));
        let small = area(2560.0, 0.0, 1920.0, 1032.0);
        let at = Rect { x: 2700.0, y: 40.0, w, h };
        let (to, zoom) = refit(small, 1.5, 1.5, at);
        assert_eq!(zoom, 1.0);
        assert_eq!((to.w, to.h), (1500.0, 1012.0));
        assert!(inside(small, to.x, to.y, to.w, to.h));
        // Its centre stays where it was as far as the work area allows.
        assert_eq!(to.x + to.w / 2.0, at.x + at.w / 2.0);
    }

    #[test]
    fn moved_back_to_a_bigger_work_area_the_panel_takes_the_pick_again() {
        let small = area(2560.0, 0.0, 1920.0, 1032.0);
        let (w, h, zoom) = fit(small.w, small.h, 1.5, 1.5);
        assert_eq!(zoom, 1.0);
        let big = area(0.0, 0.0, 2560.0, 1400.0);
        let (to, zoom) = refit(big, 1.0, 1.5, Rect { x: 2400.0, y: 300.0, w, h });
        assert_eq!(zoom, 1.5);
        assert_eq!((to.w, to.h), (1500.0, 1080.0));
        assert!(inside(big, to.x, to.y, to.w, to.h));
    }

    #[test]
    fn a_panel_off_its_work_area_is_brought_inside() {
        let a = area(-1280.0, 200.0, 1280.0, 672.0);
        let (to, zoom) = refit(a, 1.0, 1.0, Rect { x: -1600.0, y: 0.0, w: 1500.0, h: 1080.0 });
        assert_eq!(zoom, 1.0);
        assert_eq!((to.w, to.h), (1000.0, 652.0));
        assert!(inside(a, to.x, to.y, to.w, to.h));
    }

    #[test]
    fn only_another_monitor_or_work_area_asks_for_a_refit() {
        let home = Home { area: area(0.0, 0.0, 2560.0, 1400.0), scale: 1.0 };
        assert!(!left_home(None, home));
        assert!(!left_home(Some(home), home));
        // Another monitor.
        assert!(left_home(Some(home), Home { area: area(2560.0, 0.0, 1920.0, 1032.0), scale: 1.5 }));
        // The same monitor at another scale, or with the taskbar moved.
        assert!(left_home(Some(home), Home { scale: 1.25, ..home }));
        assert!(left_home(Some(home), Home { area: area(0.0, 0.0, 2560.0, 1360.0), ..home }));
    }

    #[test]
    fn a_1366_screen_moves_the_panel_just_clear_of_the_pet() {
        let a = area(0.0, 0.0, 1366.0, 728.0);
        let p = pet(a, 1.0);
        let (w, h) = size(a, 1.0);
        // Centred, it would cover the pet.
        let centred = Rect { x: (a.w - w) / 2.0, y: (a.h - h) / 2.0, w, h };
        assert!(centred.overlap(&p) > 0.0);
        let (x, y) = place(a, w, h, &[p], GAP, EDGE);
        assert!(inside(a, x, y, w, h));
        assert_eq!(x, p.x - GAP - w);
        assert_eq!(y, centred.y);
    }

    #[test]
    fn a_1280_screen_moves_the_panel_just_clear_of_the_pet() {
        let a = area(0.0, 0.0, 1280.0, 680.0);
        let p = pet(a, 1.0);
        let (w, h) = size(a, 1.0);
        assert!(p.x - GAP - w < (a.w - w) / 2.0);
        let (x, y) = place(a, w, h, &[p], GAP, EDGE);
        assert!(inside(a, x, y, w, h));
        assert_eq!(x, p.x - GAP - w);
        assert_eq!(Rect { x, y, w, h }.overlap(&p.grown(GAP)), 0.0);
    }

    #[test]
    fn a_wide_screen_keeps_the_panel_centred() {
        let a = area(0.0, 0.0, 1920.0, 1040.0);
        let p = pet(a, 1.0);
        let (w, h) = size(a, 1.0);
        let (x, y) = place(a, w, h, &[p], GAP, EDGE);
        assert_eq!(x, (a.w - w) / 2.0);
        assert_eq!(y, (a.h - h) / 2.0);
        assert_eq!(Rect { x, y, w, h }.overlap(&p.grown(GAP)), 0.0);
    }

    #[test]
    fn nothing_to_avoid_keeps_the_panel_centred() {
        let a = area(0.0, 0.0, 1366.0, 728.0);
        let (w, h) = size(a, 1.0);
        let (x, y) = place(a, w, h, &[], GAP, EDGE);
        assert_eq!((x, y), ((a.w - w) / 2.0, (a.h - h) / 2.0));
    }

    #[test]
    fn a_second_monitor_at_one_and_a_half_keeps_to_its_own_area() {
        // Left of the primary monitor, its work area in its own pixels.
        let a = area(-2880.0, 120.0, 2880.0, 1680.0);
        let p = pet(a, 1.5);
        let (w, h) = size(a, 1.5);
        let (x, y) = place(a, w, h, &[p], GAP * 1.5, EDGE * 1.5);
        assert!(inside(a, x, y, w, h));
        assert_eq!(Rect { x, y, w, h }.overlap(&p.grown(GAP * 1.5)), 0.0);
    }

    #[test]
    fn a_pet_left_of_centre_sends_the_panel_elsewhere() {
        let a = area(0.0, 0.0, 1920.0, 1040.0);
        let p = Rect { x: 300.0, y: 400.0, w: 180.0, h: 240.0 };
        let (w, h) = size(a, 1.0);
        let (x, y) = place(a, w, h, &[p], GAP, EDGE);
        assert!(inside(a, x, y, w, h));
        assert_eq!(Rect { x, y, w, h }.overlap(&p.grown(GAP)), 0.0);
    }

    #[test]
    fn a_screen_too_small_covers_the_least() {
        // 1280×720 at 125%: the panel nearly fills the work area.
        let a = area(0.0, 0.0, 1024.0, 548.0);
        let p = pet(a, 1.0);
        let (w, h) = size(a, 1.0);
        let (x, y) = place(a, w, h, &[p], GAP, EDGE);
        assert!(inside(a, x, y, w, h));
        let grown = [p.grown(GAP)];
        let ours = covered(&Rect { x, y, w, h }, &grown);
        // Every whole-pixel spot within the same margins.
        let (mx, my) = (EDGE.min((a.w - w) / 2.0), EDGE.min((a.h - h) / 2.0));
        let mut least = f64::INFINITY;
        let mut gx = a.x + mx;
        while gx + w <= a.right() - mx {
            let mut gy = a.y + my;
            while gy + h <= a.bottom() - my {
                least = least.min(covered(&Rect { x: gx, y: gy, w, h }, &grown));
                gy += 1.0;
            }
            gx += 1.0;
        }
        assert!(ours <= least + 1.0, "covers {ours}, least possible {least}");
    }
}
