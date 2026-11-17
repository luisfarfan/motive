mod canvas;
mod geometry;
use geometry::*;
// UI drafts are never an alternative Scene Graph. One validated core command
// commits a gesture; external revisions invalidate drafts and undo history.
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
            safe: crate::ui::preferences::Preferences::load().safe_margin,
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
    pub(super) fn safe_margin(&self) -> bool {
        self.editor.safe
    }
    pub(super) fn toggle_safe(&mut self) {
        self.editor.safe = !self.editor.safe;
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
