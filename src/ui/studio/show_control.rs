//! Presentation of the owner's live scheduler. No local rule execution,
//! cooldown clock, trusted event flag or cloneable confirmation authority.
use super::*;
use crate::core::show_control::{ConfigurationGuard, LocalDeckConfirmation, ShowControlCommand};
use gpui_kit::component::{
    WindowExt,
    dialog::{DialogAction, DialogButtonProps, DialogClose, DialogFooter},
};
use motive_show_control::{
    actions::Action,
    deck::{ButtonState, Deck, DeckHistory, DeckIcon, Shortcut},
    runtime::JobState,
};
use std::{cell::RefCell, rc::Rc};

#[derive(Default)]
pub(super) struct DeckUi {
    next_event: u64,
}
#[derive(serde::Deserialize)]
struct JobView {
    id: u64,
    rule_id: String,
    state: JobState,
    records: Vec<RecordView>,
}
#[derive(serde::Deserialize)]
struct RecordView {
    code: Option<String>,
}
impl DeckUi {
    fn event_id(&mut self) -> Option<String> {
        self.next_event = self.next_event.checked_add(1)?;
        Some(format!("ui-{}-{}", std::process::id(), self.next_event))
    }
}

fn icon(icon: DeckIcon) -> IconName {
    match icon {
        DeckIcon::Play => IconName::Play,
        DeckIcon::Pause => IconName::Pause,
        DeckIcon::Goal => IconName::Flag,
        DeckIcon::Timer => IconName::Timer,
        DeckIcon::Scene | DeckIcon::Layers => IconName::Layers,
        DeckIcon::Spark => IconName::Sparkles,
        DeckIcon::Text => IconName::Type,
        DeckIcon::Bell => IconName::Bell,
        DeckIcon::Stop => IconName::Square,
    }
}
fn button_caption(state: &ButtonState) -> String {
    match state {
        ButtonState::Ready => "Listo".into(),
        ButtonState::Disabled => "Desactivado".into(),
        ButtonState::AwaitingConfirmation => "Requiere confirmación".into(),
        ButtonState::CoolingDown { remaining_ms } => {
            format!("Espera {} s", remaining_ms.div_ceil(1000))
        }
        ButtonState::Pending { request_id } => format!("En curso · solicitud {request_id}"),
        ButtonState::Simulated => "Simulado".into(),
        ButtonState::Completed => "Acción finalizada".into(),
        ButtonState::NeedsReconciliation => "Resultado pendiente de revisión".into(),
        ButtonState::Rejected { code } => format!("Rechazado · {code}"),
        ButtonState::Cancelled => "Cancelado".into(),
    }
}
fn job_caption(state: &JobState) -> &'static str {
    match state {
        JobState::Queued => "En cola",
        JobState::Deferred => "Esperando disponibilidad",
        JobState::Running => "En curso",
        JobState::AwaitingCompletion => "Esperando finalización",
        JobState::Completed => "Acción finalizada",
        JobState::Simulated => "Simulado",
        JobState::Rejected => "Rechazado",
        JobState::Failed => "Falló",
        JobState::Cancelled => "Cancelado",
        JobState::TimedOut => "Tiempo agotado",
        JobState::NeedsReconciliation => "Revisar resultado",
    }
}
fn shortcut_caption(shortcut: &Shortcut) -> String {
    format!(
        "{}{}{}{}",
        if shortcut.command { "⌘" } else { "" },
        if shortcut.option { "⌥" } else { "" },
        if shortcut.shift { "⇧" } else { "" },
        shortcut.key.to_uppercase()
    )
}
fn action_caption(action: &Action) -> String {
    match action {
        Action::ShowOverlay { source_id } => format!("Mostrar overlay {source_id}"),
        Action::HideOverlay { source_id } => format!("Ocultar overlay {source_id}"),
        Action::Widget { source_id, event } => format!("Actualizar widget {source_id}: {event:?}"),
        Action::Animate {
            layer_id,
            animation,
            ..
        } => format!(
            "Animar capa {layer_id} durante {} ms",
            animation.duration_ms
        ),
        Action::TriggerAnimatedWidget {
            source_id,
            layer_id,
            animation,
            ..
        } => format!(
            "Activar widget {source_id} y animar capa {layer_id} durante {} ms",
            animation.duration_ms
        ),
        Action::CancelAnimation { operation_id } => format!("Cancelar animación {operation_id}"),
        Action::CountdownStart { source_id } => format!("Iniciar cuenta atrás {source_id}"),
        Action::CountdownReset { source_id } => format!("Reiniciar cuenta atrás {source_id}"),
        Action::SelectScene {
            scene_id,
            transition,
        } => format!("Cambiar a escena {scene_id} ({:?})", transition.kind),
        Action::UpdateText { source_id, text } => format!("Texto en {source_id}: {text}"),
        Action::IncrementCounter { name, amount } => format!("Contador {name}: {amount:+}"),
        Action::Notify { message } => format!("Aviso: {message}"),
        Action::PrepareSpeech { text } => format!("Preparar texto de voz sin reproducir: {text}"),
        Action::Sound { resource } => format!("Sonido: {resource}"),
        Action::Sequence { actions } => format!("Secuencia de {} acciones", actions.len()),
        Action::EmitEvent { name } => format!("Evento: {name}"),
    }
}

impl Studio {
    fn deck_closing(&self) -> bool {
        self.production.shutdown_requested
            || self.production.status()["output_lifecycle"]["shutdown_pending"] == true
    }
    fn show_control_command(&mut self, command: ShowControlCommand, cx: &mut Context<Self>) {
        self.command(Command::ShowControl(command), "UI", cx);
    }
    fn deck_error(&mut self, error: motive_show_control::model::Error, cx: &mut Context<Self>) {
        self.message = format!("{} · {}", error.code, error.message);
        cx.notify();
    }
    pub(super) fn live_deck_panel(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let snapshot = self.production.show_control_status();
        let configured = snapshot["configured"] == true;
        let armed = snapshot["armed"] == true;
        let bindings_current = snapshot["bindings_current"] == true;
        let closing = self.deck_closing();
        let guard = ConfigurationGuard {
            pid: std::process::id(),
            revision: self.production.revision,
            session: snapshot["session"].as_str().unwrap_or_default().into(),
        };
        let mut body = col().gap(px(10.)).on_key_down(cx.listener(Self::live_deck_key))
            .child(self.matchday_card(cx))
            .child(label(if armed { "Producción activada" } else { "Producción desactivada" }, if armed { p.ready } else { p.warn }))
            .child(label("Los botones controlan esta producción. Los atajos funcionan cuando el foco está dentro de Live Deck.", p.secondary))
            .child(row()
                .child(quiet("save-show-control", "Guardar").disabled(!configured || closing)
                    .on_click(cx.listener(move |view, _, _, cx| view.show_control_command(ShowControlCommand::SaveShowControl { expected: Some(guard.clone()) }, cx))))
                .child(quiet("load-show-control", "Restaurar…").disabled(closing)
                    .on_click(cx.listener(|view, _, window, cx| view.confirm_load_deck(window, cx))))
                .child(quiet("arm-show-control", "Activar producción").disabled(!configured || armed || closing)
                    .on_click(cx.listener(|view, _, _, cx| {
                        view.show_control_command(ShowControlCommand::ArmShowControl {
                            pid: std::process::id(), revision: view.production.revision,
                        }, cx);
                    }))));
        if let Some(sequence) = snapshot["last_save"]["sequence"].as_u64() {
            body = body.child(label(
                format!(
                    "Configuración guardada · recibo {sequence} · revisión {}",
                    snapshot["last_save"]["revision"]
                ),
                p.ready,
            ));
        }
        if let Some(error) = snapshot["last_save_error"].as_str() {
            body = body.child(label(format!("No se pudo guardar · {error}"), p.warn));
        }
        if let Some(failure) = snapshot["failure"].as_str() {
            body = body.child(label(
                format!("{failure} · Revisa los trabajos y el registro antes de continuar."),
                p.warn,
            ));
        }
        if configured && !bindings_current {
            body = body.child(label("La composición cambió. Revisa y vuelve a vincular la producción antes de activarla.", p.warn));
        }
        let Ok(mut deck) = serde_json::from_value::<Deck>(snapshot["deck"].clone()) else {
            return body.child(label("No hay una producción vinculada. Instala un Creator Pack compatible o restaura una configuración guardada.", p.secondary));
        };
        body = body.child(label(deck.name.clone(), p.ink).font_weight(FontWeight::SEMIBOLD));
        deck.groups.sort_by_key(|group| group.order);
        for group in &deck.groups {
            let mut buttons: Vec<_> = deck
                .buttons
                .iter()
                .filter(|button| button.group_id == group.id)
                .collect();
            buttons.sort_by_key(|button| button.order);
            let mut grid = row().flex_wrap().items_start();
            for button in buttons {
                let state = snapshot["buttons"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .find(|state| state["id"] == button.id)
                    .and_then(|state| {
                        serde_json::from_value::<ButtonState>(state["state"].clone()).ok()
                    })
                    .unwrap_or(ButtonState::Disabled);
                let available = matches!(
                    state,
                    ButtonState::Ready | ButtonState::AwaitingConfirmation
                );
                let caption = button_caption(&state);
                let id = button.id.clone();
                let session = snapshot["session"].as_str().unwrap_or("").to_owned();
                let shortcut = button.shortcut.as_ref().map(shortcut_caption);
                grid = grid.child(
                    col()
                        .w(px(174.))
                        .gap(px(4.))
                        .child(
                            control(
                                SharedString::from(format!("deck-button-{}", button.id)),
                                button.label.clone(),
                            )
                            .icon(icon(button.icon))
                            .h(px(42.))
                            .w_full()
                            .accessibility_label(format!(
                                "{} · {}{}",
                                button.label,
                                caption,
                                if button.sensitive {
                                    " · requiere confirmación"
                                } else {
                                    ""
                                }
                            ))
                            .tooltip(button.label.clone())
                            .disabled(
                                !armed
                                    || !bindings_current
                                    || !available
                                    || closing
                                    || snapshot["failure"].is_string(),
                            )
                            .on_click(cx.listener(
                                move |view, _, window, cx| {
                                    view.press_live_deck(&id, &session, window, cx)
                                },
                            )),
                        )
                        .child(label(
                            format!(
                                "{caption}{}",
                                shortcut.map(|s| format!(" · {s}")).unwrap_or_default()
                            ),
                            p.secondary,
                        )),
                );
            }
            body = body.child(label(group.label.clone(), p.ink)).child(grid);
        }
        let jobs =
            serde_json::from_value::<Vec<JobView>>(snapshot["jobs"].clone()).unwrap_or_default();
        if !jobs.is_empty() {
            body = body.child(label("Trabajos recientes (hasta 16)", p.ink));
        }
        for job in jobs.iter().take(16) {
            let id = job.id;
            let session = snapshot["session"].as_str().unwrap_or("").to_owned();
            let mut entry = col().gap(px(4.)).child(label(
                format!(
                    "#{} · {} · {}",
                    job.id,
                    job.rule_id,
                    job_caption(&job.state)
                ),
                p.secondary,
            ));
            if let Some(code) = job.records.iter().find_map(|record| record.code.as_ref()) {
                entry = entry.child(label(code.clone(), p.warn));
            }
            if !job.state.terminal() {
                entry = entry.child(
                    quiet(
                        SharedString::from(format!("cancel-job-{id}")),
                        "Cancelar trabajo",
                    )
                    .accessibility_label(format!("Cancelar trabajo {id}"))
                    .disabled(closing)
                    .on_click(cx.listener(move |view, _, _, cx| {
                        view.show_control_command(
                            ShowControlCommand::CancelShowControl {
                                session: session.clone(),
                                job_id: id,
                            },
                            cx,
                        )
                    })),
                );
            } else if job.state == JobState::NeedsReconciliation {
                entry = entry.child(
                    quiet(
                        SharedString::from(format!("reconcile-job-{id}")),
                        "Revisar resultado",
                    )
                    .accessibility_label(format!("Revisar resultado del trabajo {id}"))
                    .disabled(closing)
                    .on_click(cx.listener(move |view, _, _, cx| {
                        view.show_control_command(
                            ShowControlCommand::ReconcileShowControl {
                                session: session.clone(),
                                job_id: id,
                            },
                            cx,
                        )
                    })),
                );
            }
            body = body.child(entry);
        }
        let history = serde_json::from_value::<Vec<DeckHistory>>(snapshot["history"].clone())
            .unwrap_or_default();
        if !history.is_empty() {
            body = body.child(label("Historial · tiempo de sesión", p.ink));
        }
        for item in history.iter().rev().take(64) {
            let title = deck
                .buttons
                .iter()
                .find(|button| button.id == item.button_id)
                .map(|button| button.label.as_str())
                .unwrap_or(&item.button_id);
            body = body.child(label(
                format!(
                    "{:.1} s · {title} · {}",
                    item.timestamp_ms as f64 / 1000.,
                    button_caption(&item.state)
                ),
                p.secondary,
            ));
        }
        body
    }

    fn live_deck_key(&mut self, event: &KeyDownEvent, window: &mut Window, cx: &mut Context<Self>) {
        if self.panel != Some(Panel::LiveDeck) || self.deck_closing() {
            return;
        }
        let modifiers = event.keystroke.modifiers;
        if modifiers.control || modifiers.function {
            return;
        }
        let snapshot = self.production.show_control_status();
        if snapshot["armed"] != true {
            return;
        }
        let Ok(deck) = serde_json::from_value::<Deck>(snapshot["deck"].clone()) else {
            return;
        };
        let button = deck.buttons.iter().find(|button| {
            button.shortcut.as_ref().is_some_and(|key| {
                key.key == event.keystroke.key
                    && key.command == modifiers.platform
                    && key.option == modifiers.alt
                    && key.shift == modifiers.shift
            })
        });
        if let Some(button) = button {
            cx.stop_propagation();
            if !event.is_held {
                self.press_live_deck(
                    &button.id,
                    snapshot["session"].as_str().unwrap_or(""),
                    window,
                    cx,
                );
            }
        }
    }

    fn press_live_deck(
        &mut self,
        id: &str,
        expected_session: &str,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let snapshot = self.production.show_control_status();
        if snapshot["session"].as_str() != Some(expected_session) {
            self.message =
                "La sesión de producción cambió. Revisa Live Deck antes de pulsar de nuevo.".into();
            cx.notify();
            return;
        }
        let Ok(deck) = serde_json::from_value::<Deck>(snapshot["deck"].clone()) else {
            return;
        };
        let Some(button) = deck.buttons.iter().find(|button| button.id == id) else {
            return;
        };
        if button.sensitive {
            match self.production.prepare_show_control_confirmation(id) {
                Ok(confirmation) => {
                    self.confirm_live_deck(confirmation, window, cx);
                }
                Err(error) => self.deck_error(error, cx),
            }
        } else {
            let Some(event_id) = self.deck_ui.event_id() else {
                self.message = "DECK_EVENT_ID_EXHAUSTED".into();
                cx.notify();
                return;
            };
            match self.production.press_show_control(id, &event_id) {
                Ok(jobs) => {
                    self.message = format!("Acción admitida · trabajos {jobs:?}");
                    cx.notify();
                }
                Err(error) => self.deck_error(error, cx),
            }
        }
    }

    fn confirm_live_deck(
        &mut self,
        confirmation: LocalDeckConfirmation,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let mut actions = Vec::new();
        for action in confirmation.actions() {
            match action.flattened() {
                Ok(flattened) => actions.extend(flattened.iter().map(action_caption)),
                Err(error) => {
                    self.deck_error(error, cx);
                    return;
                }
            }
        }
        let description = format!(
            "{}\n\n{}\n\nConfirmar envía estas acciones a la producción actual. Si el estado cambia o pasan 60 segundos, tendrás que revisarlas otra vez.",
            confirmation.label(),
            actions.join("\n")
        );
        let button_id = confirmation.button_id().to_owned();
        let confirmation = Rc::new(RefCell::new(Some(confirmation)));
        let weak = cx.entity().downgrade();
        self.panel = None;
        window.open_dialog(cx, move |dialog, _, _| {
            let confirmation = confirmation.clone();
            let weak = weak.clone();
            dialog
                .title("Confirmar acción de Live Deck")
                .child(
                    col()
                        .id("deck-confirmation-scroll")
                        .max_h(px(300.))
                        .overflow_y_scroll()
                        .child(description.clone()),
                )
                .footer(
                    DialogFooter::new()
                        .child(DialogClose::new().trigger(|b| b.label("Cancelar")))
                        .child(
                            DialogAction::new()
                                .child(control("confirm-live-deck", "Ejecutar acción")),
                        ),
                )
                .button_props(
                    DialogButtonProps::default()
                        .ok_text("Ejecutar acción")
                        .cancel_text("Cancelar")
                        .show_cancel(true)
                        .on_ok(move |_, _, cx| {
                            let Some(confirmation) = confirmation.borrow_mut().take() else {
                                return true;
                            };
                            let _ = weak.update(cx, |view, cx| {
                                let Some(event_id) = view.deck_ui.event_id() else {
                                    view.message = "DECK_EVENT_ID_EXHAUSTED".into();
                                    cx.notify();
                                    return;
                                };
                                match view
                                    .production
                                    .confirm_show_control_local(confirmation, &event_id)
                                {
                                    Ok(jobs) => {
                                        view.message =
                                            format!("Acción admitida · trabajos {jobs:?}");
                                        cx.notify();
                                    }
                                    Err(error) => view.deck_error(error, cx),
                                }
                            });
                            true
                        }),
                )
        });
        self.message = format!("Revisión local pendiente: {button_id}");
        cx.notify();
    }

    fn confirm_load_deck(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let expected = Rc::new(RefCell::new(Some(self.production.revision)));
        let weak = cx.entity().downgrade();
        self.panel = None;
        window.open_dialog(cx, move |dialog, _, _| {
            let expected=expected.clone();let weak=weak.clone();
            dialog.title("Restaurar Show Control")
                .child("Reemplaza la configuración y Live Deck por la copia guardada. La producción se restaura desactivada; no ejecuta trabajos ni inicia salidas.")
                .footer(DialogFooter::new().child(DialogClose::new().trigger(|b|b.label("Cancelar")))
                    .child(DialogAction::new().child(control("confirm-load-deck", "Restaurar"))))
                .button_props(DialogButtonProps::default().ok_text("Restaurar").cancel_text("Cancelar").show_cancel(true)
                    .on_ok(move|_,_,cx| {
                        let Some(revision)=expected.borrow_mut().take() else{return true;};
                        let _=weak.update(cx,|view,cx| {
                            if view.production.revision!=revision {view.message="La producción cambió; vuelve a revisar la restauración.".into();cx.notify();return;}
                            view.show_control_command(ShowControlCommand::LoadShowControl,cx);
                        });true
                    }))
        });
        cx.notify();
    }
}
