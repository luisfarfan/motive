use super::*;
use crate::core::overlays::{Alignment, Definition, Font};
use gpui_kit::component::{Sizable, input::Textarea};

pub(in crate::ui::studio) fn kind_label(d: &Definition) -> &'static str {
    match d {
        Definition::Text { .. } => "Texto",
        Definition::Image { .. } => "Imagen",
        Definition::Video { .. } => "Video sin audio",
        Definition::Shape { .. } => "Forma",
        Definition::Widget { widget } => match widget.kind {
            crate::core::overlays::WidgetKind::LowerThird => "Lower third",
            crate::core::overlays::WidgetKind::Countdown => "Cuenta regresiva",
            crate::core::overlays::WidgetKind::Alert => "Alerta local",
        },
    }
}
impl Studio {
    pub(super) fn begin_overlay_draft(
        &mut self,
        definition: Definition,
        source_id: Option<String>,
        name: String,
        w: &mut Window,
        cx: &mut Context<Self>,
    ) {
        self.creative.draft = Some(draft::Draft::new(
            definition,
            source_id,
            self.production.graph().active_scene.clone(),
            self.production.revision,
            name,
            w,
            cx,
        ));
        self.creative.editor_tab = EditorTab::Content;
        self.creative.animation = Some(runtime::AnimationDraft::new(w, cx));
        cx.notify();
    }
    pub(super) fn edit_overlay(&mut self, id: &str, w: &mut Window, cx: &mut Context<Self>) {
        if let Some(source) = self
            .production
            .graph()
            .sources
            .iter()
            .find(|s| s.id == id)
            .cloned()
            && let Some(definition) = source.overlay
        {
            self.begin_overlay_draft(definition, Some(source.id), source.name, w, cx);
        }
    }
    pub(in crate::ui::studio) fn prepare_overlay_inspector(
        &mut self,
        w: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if self.panel != Some(Panel::Layer) {
            return;
        }
        self.creative.draft = None;
        let id = self
            .production
            .graph()
            .scene(&self.production.graph().active_scene)
            .ok()
            .and_then(|s| {
                s.layers
                    .iter()
                    .find(|l| Some(&l.id) == self.selected_layer.as_ref())
            })
            .map(|l| l.source_id.clone());
        if let Some(id) = id {
            self.edit_overlay(&id, w, cx);
        }
    }
    fn submit_overlay(&mut self, w: &mut Window, cx: &mut Context<Self>) {
        let Some(draft) = &self.creative.draft else {
            return;
        };
        if draft.revision != self.production.revision {
            self.message="El núcleo cambió. Recarga este inspector antes de aplicar; tu borrador no se ha enviado.".into();
            cx.notify();
            return;
        }
        let definition = match draft.definition(cx) {
            Ok(d) => d,
            Err(e) => {
                self.message = e.to_string();
                cx.notify();
                return;
            }
        };
        let source_id = draft.source_id.clone();
        let command = match &source_id {
            Some(id) => OverlayCommand::UpdateOverlay {
                source_id: id.clone(),
                definition,
            },
            None => OverlayCommand::CreateOverlay {
                scene_id: draft.scene_id.clone(),
                name: draft.value(draft::Field::Name, cx),
                definition,
            },
        };
        let result = self.command(Command::Overlay(command), "UI", cx);
        if result["ok"] == true {
            let id =
                source_id.or_else(|| result["result"]["source_id"].as_str().map(str::to_owned));
            if let Some(id) = id {
                self.selected_layer = self
                    .production
                    .graph()
                    .scene(&self.production.graph().active_scene)
                    .ok()
                    .and_then(|s| s.layers.iter().find(|l| l.source_id == id))
                    .map(|l| l.id.clone());
                self.edit_overlay(&id, w, cx);
            }
        }
    }
    pub(in crate::ui::studio) fn creative_inspector(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let Some(draft) = &self.creative.draft else {
            return col().child(label("Selecciona un overlay de la biblioteca.", p.muted));
        };
        let existing = draft.source_id.is_some();
        let stale = draft.revision != self.production.revision;
        let mut body = col().gap(px(10.)).child(label(
            format!(
                "{} · {}",
                kind_label(&draft.definition),
                if existing {
                    "propiedades compartidas entre escenas"
                } else {
                    "nueva fuente"
                }
            ),
            p.secondary,
        ));
        if self.panel == Some(Panel::Creative) {
            body = body.child(quiet("back-to-library", "Volver a la biblioteca").on_click(
                cx.listener(|v, _, _, cx| {
                    v.creative.draft = None;
                    cx.notify();
                }),
            ));
        }
        if existing {
            body = body.child(
                row().children(
                    [
                        (EditorTab::Content, "Contenido"),
                        (EditorTab::Live, "En vivo"),
                        (EditorTab::Animation, "Animación"),
                    ]
                    .into_iter()
                    .enumerate()
                    .map(|(i, (tab, name))| {
                        quiet(("overlay-editor-tab", i), name)
                            .selected(self.creative.editor_tab == tab)
                            .on_click(cx.listener(move |v, _, _, cx| {
                                v.creative.editor_tab = tab;
                                cx.notify();
                            }))
                    }),
                ),
            );
        }
        if existing && self.creative.editor_tab == EditorTab::Live {
            return body.child(self.overlay_live_controls(cx));
        }
        if existing && self.creative.editor_tab == EditorTab::Animation {
            return body.child(self.overlay_animation_controls(cx));
        }
        if stale {
            let id = draft.source_id.clone();
            let definition = draft.definition.clone();
            body=body.child(label("El núcleo cambió. Recarga para revisar los valores actuales; el borrador se descartará.",p.warn))
                .child(quiet("reload-overlay-draft","Recargar inspector").on_click(cx.listener(move|v,_,w,cx|{
                    if let Some(id)=&id {v.edit_overlay(id,w,cx);}else{v.begin_overlay_draft(definition.clone(),None,kind_label(&definition).into(),w,cx);}
                })));
        }
        let status = self.production.status();
        let structural = self.production.overlay_status()["runtime"]["animations"]["busy"] == true
            || status["transition"]["phase"] == "preparing"
            || status["transition"]["phase"] == "running";
        let blocked = stale
            || structural
            || ((!existing || matches!(draft.definition, Definition::Video { .. }))
                && status["output"] != "idle");
        body = body.child(
            control(
                "apply-overlay-definition",
                if existing {
                    "Aplicar propiedades"
                } else {
                    "Crear overlay"
                },
            )
            .disabled(blocked)
            .on_click(cx.listener(|v, _, w, cx| v.submit_overlay(w, cx))),
        );
        if matches!(
            draft.definition,
            Definition::Text { .. } | Definition::Widget { .. }
        ) {
            body = body.child(
                property_group(
                    if matches!(draft.definition, Definition::Text { .. }) {
                        "Texto (saltos de línea explícitos)"
                    } else {
                        "Título"
                    },
                    p,
                )
                .child(
                    Textarea::new(&draft.text)
                        .aria_label("Texto del overlay")
                        .small()
                        .w_full(),
                ),
            );
        }
        if matches!(draft.definition, Definition::Widget { .. }) {
            body = body.child(
                property_group("Subtítulo", p).child(
                    Textarea::new(&draft.subtitle)
                        .aria_label("Subtítulo del widget")
                        .small()
                        .w_full(),
                ),
            );
        }
        if let Some(id) = draft.definition.asset_id() {
            body = body.child(label(format!("Recurso fijo: {id}"), p.muted));
        }
        for (key, input) in &draft.fields {
            body = body.child(forms::field(key.label(), input, p));
        }
        match &draft.definition {
            Definition::Text {
                font,
                align,
                outline,
                ..
            } => {
                body = body
                    .child(
                        property_group("Tipografía", p).child(
                            row().children(
                                [Font::Helvetica, Font::Arial, Font::Menlo]
                                    .into_iter()
                                    .enumerate()
                                    .map(|(i, f)| {
                                        quiet(("overlay-font", i), format!("{f:?}"))
                                            .selected(*font == f)
                                            .on_click(cx.listener(move |v, _, _, cx| {
                                                if let Some(d) = &mut v.creative.draft
                                                    && let Definition::Text { font, .. } =
                                                        &mut d.definition
                                                {
                                                    *font = f;
                                                }
                                                cx.notify();
                                            }))
                                    }),
                            ),
                        ),
                    )
                    .child(
                        property_group("Alineación", p).child(
                            row().children(
                                [
                                    (Alignment::Left, "Izquierda"),
                                    (Alignment::Center, "Centro"),
                                    (Alignment::Right, "Derecha"),
                                ]
                                .into_iter()
                                .enumerate()
                                .map(|(i, (a, name))| {
                                    quiet(("overlay-align", i), name)
                                        .selected(*align == a)
                                        .on_click(cx.listener(move |v, _, _, cx| {
                                            if let Some(d) = &mut v.creative.draft
                                                && let Definition::Text { align, .. } =
                                                    &mut d.definition
                                            {
                                                *align = a;
                                            }
                                            cx.notify();
                                        }))
                                }),
                            ),
                        ),
                    )
                    .child(
                        quiet(
                            "overlay-outline",
                            if *outline {
                                "Contorno activado"
                            } else {
                                "Contorno desactivado"
                            },
                        )
                        .selected(*outline)
                        .on_click(cx.listener(|v, _, _, cx| {
                            if let Some(d) = &mut v.creative.draft
                                && let Definition::Text { outline, .. } = &mut d.definition
                            {
                                *outline = !*outline;
                            }
                            cx.notify();
                        })),
                    );
            }
            Definition::Video { looping, .. } => {
                body = body.child(
                    quiet(
                        "overlay-looping",
                        if *looping {
                            "Repetición activada"
                        } else {
                            "Repetición desactivada"
                        },
                    )
                    .selected(*looping)
                    .on_click(cx.listener(|v, _, _, cx| {
                        if let Some(d) = &mut v.creative.draft
                            && let Definition::Video { looping, .. } = &mut d.definition
                        {
                            *looping = !*looping;
                        }
                        cx.notify();
                    })),
                )
            }
            _ => {}
        }
        body
    }
}
