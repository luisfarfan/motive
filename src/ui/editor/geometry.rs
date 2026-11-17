use super::{Handle, Transform};
pub(super) fn format_number(n: f32) -> String {
    // Keep the shortest round-trippable representation: focusing and pressing
    // Enter without editing must never quantize the core's f32 transform.
    n.to_string()
}
pub(super) trait Finite {
    fn filter_finite(self) -> Result<f32, ()>;
}
impl<E> Finite for Result<f32, E> {
    fn filter_finite(self) -> Result<f32, ()> {
        self.map_err(|_| ())
            .and_then(|n| if n.is_finite() { Ok(n) } else { Err(()) })
    }
}
pub(super) fn contains(t: &Transform, p: (f32, f32)) -> bool {
    t.visible && p.0 >= t.x && p.0 <= t.x + t.width && p.1 >= t.y && p.1 <= t.y + t.height
}
pub(super) fn hit_handle(t: &Transform, p: (f32, f32), r: f32) -> Option<Handle> {
    if !t.visible {
        return None;
    }
    [
        (0., 0., Handle::Nw),
        (0.5, 0., Handle::N),
        (1., 0., Handle::Ne),
        (1., 0.5, Handle::E),
        (1., 1., Handle::Se),
        (0.5, 1., Handle::S),
        (0., 1., Handle::Sw),
        (0., 0.5, Handle::W),
    ]
    .into_iter()
    .find(|(x, y, _)| {
        (p.0 - (t.x + x * t.width)).abs() <= r && (p.1 - (t.y + y * t.height)).abs() <= r
    })
    .map(|(_, _, h)| h)
}
pub(super) fn snap(pos: f32, size: f32, lines: &[f32], threshold: f32) -> (f32, Option<f32>) {
    let mut best = threshold;
    let mut delta = 0.;
    let mut guide = None;
    for line in lines {
        for edge in [pos, pos + size / 2., pos + size] {
            let d = line - edge;
            if d.abs() < best {
                best = d.abs();
                delta = d;
                guide = Some(*line);
            }
        }
    }
    (pos + delta, guide)
}
pub(super) fn drag_rect(
    t: &Transform,
    h: Handle,
    (mut dx, mut dy): (f32, f32),
    shift: bool,
) -> Transform {
    let mut n = t.clone();
    if h == Handle::Move {
        if shift {
            if dx.abs() >= dy.abs() {
                dy = 0.
            } else {
                dx = 0.
            }
        }
        n.x = (n.x + dx).clamp(-4096., 4096.);
        n.y = (n.y + dy).clamp(-4096., 4096.);
        return n;
    }
    let west = matches!(h, Handle::Nw | Handle::W | Handle::Sw);
    let north = matches!(h, Handle::Nw | Handle::N | Handle::Ne);
    if !matches!(h, Handle::N | Handle::S) {
        n.width = (t.width + if west { -dx } else { dx }).clamp(1., 4096.);
    }
    if !matches!(h, Handle::E | Handle::W) {
        n.height = (t.height + if north { -dy } else { dy }).clamp(1., 4096.);
    }
    if !shift && matches!(h, Handle::Nw | Handle::Ne | Handle::Se | Handle::Sw) {
        let factor = if (dx / t.width).abs() >= (dy / t.height).abs() {
            n.width / t.width
        } else {
            n.height / t.height
        };
        let factor = factor.clamp(
            (1. / t.width).max(1. / t.height),
            (4096. / t.width).min(4096. / t.height),
        );
        n.width = t.width * factor;
        n.height = t.height * factor;
    }
    if west {
        n.x = t.x + t.width - n.width;
    }
    if north {
        n.y = t.y + t.height - n.height;
    }
    n
}
#[cfg(test)]
mod tests {
    #[test]
    pub(super) fn numeric_field_roundtrip_preserves_transform_precision() {
        for n in [64.125_f32, 32.0001, -0.125, 960.0, 0.000_001, 1234.5679] {
            assert_eq!(super::format_number(n).parse::<f32>().unwrap(), n);
        }
    }

    use super::{Finite, Handle, Transform, contains, drag_rect, hit_handle, snap};
    pub(super) fn rect() -> Transform {
        Transform::rect(40., 50., 200., 100., 2)
    }
    #[test]
    pub(super) fn move_shift_locks_dominant_axis() {
        let n = drag_rect(&rect(), Handle::Move, (22., 4.), true);
        assert_eq!((n.x, n.y), (62., 50.));
    }
    #[test]
    pub(super) fn corner_preserves_aspect_and_opposite_anchor() {
        let n = drag_rect(&rect(), Handle::Nw, (-40., -10.), false);
        for (actual, expected) in [n.x, n.y, n.width, n.height]
            .into_iter()
            .zip([0., 30., 240., 120.])
        {
            assert!((actual - expected).abs() < 0.001);
        }
    }
    #[test]
    pub(super) fn shift_corner_allows_independent_size() {
        let n = drag_rect(&rect(), Handle::Se, (40., 10.), true);
        assert_eq!((n.width, n.height), (240., 110.));
    }
    #[test]
    pub(super) fn cannot_flip_or_exceed_core_size_limits() {
        let n = drag_rect(&rect(), Handle::Nw, (1000., 1000.), true);
        assert_eq!((n.width, n.height), (1., 1.));
        assert!(n.validate().is_ok());
        let n = drag_rect(&rect(), Handle::Se, (10000., 10000.), false);
        assert_eq!(n.width / n.height, 2.);
        assert!(n.validate().is_ok());
    }
    #[test]
    pub(super) fn snap_supports_center_edges_and_safe_margin() {
        assert_eq!(snap(37., 200., &[32., 480.], 6.), (32., Some(32.)));
        assert_eq!(snap(382., 200., &[480.], 6.), (380., Some(480.)));
        assert_eq!(snap(400., 200., &[480.], 6.), (400., None));
    }
    #[test]
    pub(super) fn hidden_layers_are_not_hit_targets() {
        let mut t = rect();
        assert!(contains(&t, (50., 60.)));
        t.visible = false;
        assert!(!contains(&t, (50., 60.)));
        assert!(hit_handle(&t, (40., 50.), 8.).is_none());
    }
    #[test]
    pub(super) fn number_input_rejects_nan_and_infinity() {
        for s in ["NaN", "inf", "-inf", "oops"] {
            assert!(s.parse::<f32>().filter_finite().is_err());
        }
    }
}
