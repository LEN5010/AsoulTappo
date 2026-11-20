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

    /// The panel's size on a monitor (lib.rs, open_panel).
    fn size(a: Rect, scale: f64) -> (f64, f64) {
        ((1000.0 * scale).min(a.w - 20.0), (720.0 * scale).min(a.h - 20.0))
    }

    fn inside(a: Rect, x: f64, y: f64, w: f64, h: f64) -> bool {
        x >= a.x && y >= a.y && x + w <= a.right() && y + h <= a.bottom()
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
