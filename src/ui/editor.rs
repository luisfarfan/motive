//! UI drafts are never an alternative Scene Graph. One validated core command
//! commits a gesture; external revisions invalidate drafts and undo history.
use super::*;
use crate::scene::Transform;
use gpui_kit::component::{
    Sizable,
    input::{Input, InputEvent, InputState},
};
use std::{cell::Cell, rc::Rc};

#[derive(Clone, Debug)]
pub(super) struct Edit {
    scene: String,
    layer: String,
    variant: Variant,
    before: Transform,
    after: Transform,
}
#[derive(Clone, Copy, Debug, PartialEq)]
enum Handle {
    Move,
    Nw,
    N,
    Ne,
    E,
    Se,
    S,
    Sw,
    W,
}
#[derive(Clone)]
struct Drag {
    edit: Edit,
    start: (f32, f32),
    handle: Handle,
    revision: u64,
    guides: (Option<f32>, Option<f32>),
}
pub(super) struct Editor {
    fields: [Entity<InputState>; 4],
    field_edit: Option<(Edit, u64)>,
    bounds: Rc<Cell<Bounds<Pixels>>>,
    drag: Option<Drag>,
    undo: Vec<Edit>,
    redo: Vec<Edit>,
    revision: u64,
    safe: bool,
    hot: bool,
}
impl Editor {
    pub(super) fn new(window: &mut Window, cx: &mut Context<Studio>) -> Self {
        let fields = std::array::from_fn(|i| {
            let input = cx.new(|cx| InputState::new(window, cx));
            cx.subscribe_in(&input, window, move |v, _, event, w, cx| match event {
                InputEvent::Focus => {
                    v.editor.field_edit = v.selected_edit().map(|e| (e, v.production.revision))
                }
                InputEvent::PressEnter { .. } => {
                    v.commit_field(i, w, cx);
                }
                InputEvent::Blur => {
                    v.editor.field_edit = None;
                    cx.notify();
                }
                _ => {}
            })
            .detach();
            input
        });
        Self {
            fields,
            field_edit: None,
            bounds: Rc::new(Cell::new(Bounds::default())),
            drag: None,
            undo: vec![],
            redo: vec![],
            revision: 0,
            safe: false,
            hot: false,
        }
    }
}
impl Studio {
    fn selected_edit(&self) -> Option<Edit> {
        let g = self.production.graph();
        let s = g.scene(&g.active_scene).ok()?;
        let l = s
            .layers
            .iter()
            .find(|l| Some(&l.id) == self.selected_layer.as_ref())?;
        let t = l.layouts.get(self.production.project.variant).clone();
        Some(Edit {
            scene: s.id.clone(),
            layer: l.id.clone(),
            variant: self.production.project.variant,
            before: t.clone(),
            after: t,
        })
    }
    fn matches_edit(&self, e: &Edit, expected: &Transform) -> bool {
        let g = self.production.graph();
        g.active_scene == e.scene
            && self.production.project.variant == e.variant
            && g.scene(&e.scene)
                .ok()
                .and_then(|s| s.layers.iter().find(|l| l.id == e.layer))
                .is_some_and(|l| l.layouts.get(e.variant) == expected)
    }
    fn apply_edit(&mut self, e: Edit, revision: u64, cx: &mut Context<Self>) -> bool {
        if self.production.revision != revision || !self.matches_edit(&e, &e.before) {
            self.message = "La composición cambió. Se descartó la edición pendiente.".into();
            cx.notify();
            return false;
        }
        if e.before == e.after {
            return true;
        }
        if self.editor.revision != revision {
            self.editor.undo.clear();
            self.editor.redo.clear();
        }
        let r = self.command(
            Command::SetTransform {
                scene_id: e.scene.clone(),
                layer_id: e.layer.clone(),
                variant: e.variant,
                transform: e.after.clone(),
            },
            "UI",
            cx,
        );
        if r["ok"] == true {
            self.editor.undo.push(e);
            if self.editor.undo.len() > 100 {
                self.editor.undo.remove(0);
            }
            self.editor.redo.clear();
            self.editor.revision = self.production.revision;
            true
        } else {
            false
        }
    }
    fn undo_edit(&mut self, redo: bool, cx: &mut Context<Self>) {
        if self.editor.revision != self.production.revision {
            self.editor.undo.clear();
            self.editor.redo.clear();
            self.message = "El núcleo cambió; el historial local ya no es aplicable.".into();
            cx.notify();
            return;
        }
        let e = if redo {
            self.editor.redo.last()
        } else {
            self.editor.undo.last()
        }
        .cloned();
        let Some(e) = e else { return };
        let expected = if redo { &e.before } else { &e.after };
        if !self.matches_edit(&e, expected) {
            self.editor.undo.clear();
            self.editor.redo.clear();
            return;
        }
        let transform = if redo {
            e.after.clone()
        } else {
            e.before.clone()
        };
        if self.command(
            Command::SetTransform {
                scene_id: e.scene.clone(),
                layer_id: e.layer.clone(),
                variant: e.variant,
                transform,
            },
            "UI",
            cx,
        )["ok"]
            == true
        {
            if redo {
                self.editor.redo.pop();
                self.editor.undo.push(e);
            } else {
                self.editor.undo.pop();
                self.editor.redo.push(e);
            }
            self.editor.revision = self.production.revision;
        }
    }
    pub(super) fn sync_fields(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        if self
            .editor
            .drag
            .as_ref()
            .is_some_and(|d| d.revision != self.production.revision)
        {
            self.editor.drag = None;
            self.message = "El núcleo cambió durante el gesto; edición descartada.".into();
        }
        if let Some(e) = self.selected_edit() {
            for (i, n) in [e.before.x, e.before.y, e.before.width, e.before.height]
                .into_iter()
                .enumerate()
            {
                let input = &self.editor.fields[i];
                if !input.read(cx).focus_handle(cx).is_focused(window) {
                    let text = format_number(n);
                    if input.read(cx).value() != text {
                        input.update(cx, |s, cx| s.set_value(text, window, cx));
                    }
                }
            }
        }
    }
    fn commit_field(&mut self, i: usize, window: &mut Window, cx: &mut Context<Self>) {
        let Some((mut e, revision)) = self.editor.field_edit.clone() else {
            return;
        };
        let value = self.editor.fields[i].read(cx).value().parse::<f32>();
        let Ok(value) = value.filter_finite() else {
            self.message = "Usa un número finito; Enter aplica y Esc descarta.".into();
            cx.notify();
            return;
        };
        match i {
            0 => e.after.x = value,
            1 => e.after.y = value,
            2 => e.after.width = value,
            _ => e.after.height = value,
        };
        if self.apply_edit(e, revision, cx) {
            self.editor.field_edit = self.selected_edit().map(|e| (e, self.production.revision));
            self.focus.focus(window, cx);
        }
    }
    pub(super) fn field_focused(&self, window: &Window, cx: &App) -> bool {
        self.editor
            .fields
            .iter()
            .any(|f| f.read(cx).focus_handle(cx).is_focused(window))
    }
    pub(super) fn inspector(&self, _cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        row().gap(px(4.)).children(
            [
                ("X", "Posición X"),
                ("Y", "Posición Y"),
                ("An", "Ancho"),
                ("Al", "Alto"),
            ]
            .into_iter()
            .enumerate()
            .map(|(i, (short, name))| {
                row()
                    .gap(px(2.))
                    .child(label(short, p.muted).text_size(px(12.)))
                    .child(
                        Input::new(&self.editor.fields[i])
                            .aria_label(name)
                            .small()
                            .w(px(72.))
                            .h(px(26.))
                            .appearance(false)
                            .focus_bordered(true),
                    )
            }),
        )
    }
    pub(super) fn canvas_view(&self, pw: f32, ph: f32, cx: &mut Context<Self>) -> impl IntoElement {
        let bounds = self.editor.bounds.clone();
        let scale = pw / self.production.engine.width as f32;
        let selected = self
            .editor
            .drag
            .as_ref()
            .map(|d| d.edit.after.clone())
            .or_else(|| self.selected_edit().map(|e| e.before));
        div()
            .id("program-canvas")
            .relative()
            .w(px(pw))
            .h(px(ph))
            .bg(rgb(0x0e0f12))
            .cursor_crosshair()
            .on_hover(cx.listener(|v, hot, _, cx| {
                if v.editor.hot != *hot {
                    v.editor.hot = *hot;
                    cx.notify();
                }
            }))
            .on_mouse_down(
                MouseButton::Left,
                cx.listener(|v, e, w, cx| v.begin_drag(e, w, cx)),
            )
            .children(
                self.frame
                    .clone()
                    .map(|f| img(f).size_full().object_fit(ObjectFit::Contain)),
            )
            .child(
                canvas(
                    move |b, _, _| {
                        bounds.set(b);
                    },
                    |_, _, _, _| {},
                )
                .absolute()
                .inset_0(),
            )
            .when(self.editor.safe, |d| {
                d.child(
                    div()
                        .absolute()
                        .left(px(32. * scale))
                        .top(px(32. * scale))
                        .w(px(pw - 64. * scale))
                        .h(px(ph - 64. * scale))
                        .border_1()
                        .border_color(rgba(0xffffff55)),
                )
            })
            .children(selected.filter(|t| t.visible).map(|t| {
                let mut selection = div()
                    .absolute()
                    .left(px(t.x * scale))
                    .top(px(t.y * scale))
                    .w(px(t.width * scale))
                    .h(px(t.height * scale));
                for (left, top) in [(true, true), (false, true), (true, false), (false, false)] {
                    selection = selection.child(
                        div()
                            .absolute()
                            .size(px(14.))
                            .border_color(rgb(0xffffff))
                            .when(left, |d| d.left(px(-3.)).border_l_2())
                            .when(!left, |d| d.right(px(-3.)).border_r_2())
                            .when(top, |d| d.top(px(-3.)).border_t_2())
                            .when(!top, |d| d.bottom(px(-3.)).border_b_2()),
                    );
                }
                selection.when(self.editor.hot || self.editor.drag.is_some(), |d| {
                    d.children(
                        [
                            (0., 0.),
                            (0.5, 0.),
                            (1., 0.),
                            (1., 0.5),
                            (1., 1.),
                            (0.5, 1.),
                            (0., 1.),
                            (0., 0.5),
                        ]
                        .into_iter()
                        .map(|(x, y)| {
                            div()
                                .absolute()
                                .left(px(x * t.width * scale - 3.))
                                .top(px(y * t.height * scale - 3.))
                                .size(px(6.))
                                .bg(rgb(0xffffff))
                                .border_1()
                                .border_color(rgb(0x16181d))
                        }),
                    )
                })
            }))
            .children(self.editor.drag.as_ref().and_then(|d| d.guides.0).map(|x| {
                div()
                    .absolute()
                    .left(px(x * scale))
                    .top_0()
                    .w(px(1.))
                    .h(px(ph))
                    .bg(rgb(0x0a7aff))
            }))
            .children(self.editor.drag.as_ref().and_then(|d| d.guides.1).map(|y| {
                div()
                    .absolute()
                    .top(px(y * scale))
                    .left_0()
                    .h(px(1.))
                    .w(px(pw))
                    .bg(rgb(0x0a7aff))
            }))
            .when(self.editor.drag.is_some(), |d| {
                d.child(
                    label("Vista de edición · aplicar al soltar", rgb(0xffffff))
                        .absolute()
                        .top(px(8.))
                        .left(px(8.))
                        .px(px(8.))
                        .py(px(4.))
                        .rounded(px(5.))
                        .bg(rgba(0x000000cc)),
                )
            })
    }
    fn program_point(&self, p: Point<Pixels>) -> (f32, f32) {
        let b = self.editor.bounds.get();
        let scale = f32::from(b.size.width) / self.production.engine.width as f32;
        (
            f32::from(p.x - b.origin.x) / scale,
            f32::from(p.y - b.origin.y) / scale,
        )
    }
    fn begin_drag(&mut self, event: &MouseDownEvent, window: &mut Window, cx: &mut Context<Self>) {
        if self.panel.is_some() {
            return;
        }
        self.focus.focus(window, cx);
        let point = self.program_point(event.position);
        let scale =
            f32::from(self.editor.bounds.get().size.width) / self.production.engine.width as f32;
        let selected = self.selected_edit();
        let handle = selected
            .as_ref()
            .and_then(|e| hit_handle(&e.before, point, 8. / scale));
        if handle.is_none() {
            let g = self.production.graph();
            let s = g.scene(&g.active_scene).unwrap();
            self.selected_layer = s
                .layers
                .iter()
                .filter(|l| contains(l.layouts.get(self.production.project.variant), point))
                .max_by_key(|l| l.layouts.get(self.production.project.variant).order)
                .map(|l| l.id.clone());
        }
        self.editor.drag = self.selected_edit().map(|e| Drag {
            edit: e,
            start: point,
            handle: handle.unwrap_or(Handle::Move),
            revision: self.production.revision,
            guides: (None, None),
        });
        cx.notify();
    }
    pub(super) fn drag_move(&mut self, event: &MouseMoveEvent, cx: &mut Context<Self>) {
        if event.pressed_button != Some(MouseButton::Left) {
            return;
        }
        let p = self.program_point(event.position);
        let Some(d) = self.editor.drag.as_mut() else {
            return;
        };
        if self.production.revision != d.revision {
            self.editor.drag = None;
            cx.notify();
            return;
        }
        let delta = (p.0 - d.start.0, p.1 - d.start.1);
        d.edit.after = drag_rect(&d.edit.before, d.handle, delta, event.modifiers.shift);
        d.guides = (None, None);
        if d.handle == Handle::Move && !event.modifiers.platform {
            let threshold = 6. * self.production.engine.width as f32
                / f32::from(self.editor.bounds.get().size.width);
            let w = self.production.engine.width as f32;
            let h = self.production.engine.height as f32;
            let (x, gx) = snap(
                d.edit.after.x,
                d.edit.after.width,
                &[0., 32., w / 2., w - 32., w],
                threshold,
            );
            let (y, gy) = snap(
                d.edit.after.y,
                d.edit.after.height,
                &[0., 32., h / 2., h - 32., h],
                threshold,
            );
            if !event.modifiers.shift || delta.0.abs() >= delta.1.abs() {
                d.edit.after.x = x;
                d.guides.0 = gx;
            }
            if !event.modifiers.shift || delta.1.abs() > delta.0.abs() {
                d.edit.after.y = y;
                d.guides.1 = gy;
            }
        }
        cx.notify();
    }
    pub(super) fn end_drag(&mut self, cx: &mut Context<Self>) {
        if let Some(d) = self.editor.drag.take() {
            self.apply_edit(d.edit, d.revision, cx);
            cx.notify();
        }
    }
    pub(super) fn editor_key(
        &mut self,
        event: &KeyDownEvent,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let key = event.keystroke.key.as_str();
        let m = event.keystroke.modifiers;
        if key == "escape" {
            self.editor.drag = None;
            self.editor.field_edit = None;
            self.panel = None;
            self.picker = None;
            self.selected_layer = None;
            self.focus.focus(window, cx);
            cx.notify();
            return;
        }
        if m.platform && key == "s" {
            self.command(Command::SaveProject, "UI", cx);
            cx.stop_propagation();
            return;
        }
        if self
            .editor
            .fields
            .iter()
            .any(|f| f.read(cx).focus_handle(cx).is_focused(window))
        {
            return;
        }
        if self.panel.is_some() {
            return;
        }
        if key == "z" && m.platform {
            self.undo_edit(m.shift, cx);
            cx.stop_propagation();
            return;
        }
        if let Ok(index) = key.parse::<usize>()
            && (1..=9).contains(&index)
        {
            if let Some(s) = self.production.graph().scenes.get(index - 1) {
                self.command(
                    Command::SelectScene {
                        scene_id: s.id.clone(),
                    },
                    "UI",
                    cx,
                );
                self.selected_layer = None;
            }
            cx.stop_propagation();
            return;
        }
        if key == "s" && m.shift {
            self.editor.safe = !self.editor.safe;
            cx.notify();
            return;
        }
        let Some(mut e) = self.selected_edit() else {
            return;
        };
        let step = if m.shift { 10. } else { 1. };
        match key {
            "left" => e.after.x -= step,
            "right" => e.after.x += step,
            "up" => e.after.y -= step,
            "down" => e.after.y += step,
            "]" if m.platform => e.after.order = (e.after.order + 1).min(31),
            "[" if m.platform => e.after.order = e.after.order.saturating_sub(1),
            _ => return,
        }
        self.apply_edit(e, self.production.revision, cx);
        cx.stop_propagation();
    }
}
fn format_number(n: f32) -> String {
    // Keep the shortest round-trippable representation: focusing and pressing
    // Enter without editing must never quantize the core's f32 transform.
    n.to_string()
}
trait Finite {
    fn filter_finite(self) -> Result<f32, ()>;
}
impl<E> Finite for Result<f32, E> {
    fn filter_finite(self) -> Result<f32, ()> {
        self.map_err(|_| ())
            .and_then(|n| if n.is_finite() { Ok(n) } else { Err(()) })
    }
}
fn contains(t: &Transform, p: (f32, f32)) -> bool {
    t.visible && p.0 >= t.x && p.0 <= t.x + t.width && p.1 >= t.y && p.1 <= t.y + t.height
}
fn hit_handle(t: &Transform, p: (f32, f32), r: f32) -> Option<Handle> {
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
fn snap(pos: f32, size: f32, lines: &[f32], threshold: f32) -> (f32, Option<f32>) {
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
fn drag_rect(t: &Transform, h: Handle, (mut dx, mut dy): (f32, f32), shift: bool) -> Transform {
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
    fn numeric_field_roundtrip_preserves_transform_precision() {
        for n in [64.125_f32, 32.0001, -0.125, 960.0, 0.000_001, 1234.5679] {
            assert_eq!(super::format_number(n).parse::<f32>().unwrap(), n);
        }
    }

    use super::{Finite, Handle, Transform, contains, drag_rect, hit_handle, snap};
    fn rect() -> Transform {
        Transform::rect(40., 50., 200., 100., 2)
    }
    #[test]
    fn move_shift_locks_dominant_axis() {
        let n = drag_rect(&rect(), Handle::Move, (22., 4.), true);
        assert_eq!((n.x, n.y), (62., 50.));
    }
    #[test]
    fn corner_preserves_aspect_and_opposite_anchor() {
        let n = drag_rect(&rect(), Handle::Nw, (-40., -10.), false);
        for (actual, expected) in [n.x, n.y, n.width, n.height]
            .into_iter()
            .zip([0., 30., 240., 120.])
        {
            assert!((actual - expected).abs() < 0.001);
        }
    }
    #[test]
    fn shift_corner_allows_independent_size() {
        let n = drag_rect(&rect(), Handle::Se, (40., 10.), true);
        assert_eq!((n.width, n.height), (240., 110.));
    }
    #[test]
    fn cannot_flip_or_exceed_core_size_limits() {
        let n = drag_rect(&rect(), Handle::Nw, (1000., 1000.), true);
        assert_eq!((n.width, n.height), (1., 1.));
        assert!(n.validate().is_ok());
        let n = drag_rect(&rect(), Handle::Se, (10000., 10000.), false);
        assert_eq!(n.width / n.height, 2.);
        assert!(n.validate().is_ok());
    }
    #[test]
    fn snap_supports_center_edges_and_safe_margin() {
        assert_eq!(snap(37., 200., &[32., 480.], 6.), (32., Some(32.)));
        assert_eq!(snap(382., 200., &[480.], 6.), (380., Some(480.)));
        assert_eq!(snap(400., 200., &[480.], 6.), (400., None));
    }
    #[test]
    fn hidden_layers_are_not_hit_targets() {
        let mut t = rect();
        assert!(contains(&t, (50., 60.)));
        t.visible = false;
        assert!(!contains(&t, (50., 60.)));
        assert!(hit_handle(&t, (40., 50.), 8.).is_none());
    }
    #[test]
    fn number_input_rejects_nan_and_infinity() {
        for s in ["NaN", "inf", "-inf", "oops"] {
            assert!(s.parse::<f32>().filter_finite().is_err());
        }
    }
}
