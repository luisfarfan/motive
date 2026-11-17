//! Application closure is a request to Production, never a native worker join.
//! Native AppKit Quit is cancelled before GPUI's non-cancellable quit observer;
//! the next owner tick receives it and follows the same confirmation path.
use super::*;
use gpui_kit::component::WindowExt;

pub(super) struct Lifecycle {
    window: AnyWindowHandle,
    confirmation_open: bool,
    pub(super) shutdown_waiting: bool,
    quit_dispatched: bool,
    diagnostics_saved: bool,
}
impl Lifecycle {
    pub(super) fn new(window: AnyWindowHandle) -> Self {
        Self {
            window,
            confirmation_open: false,
            shutdown_waiting: false,
            quit_dispatched: false,
            diagnostics_saved: false,
        }
    }
}
impl Studio {
    pub(crate) fn close_requested(&mut self, window: &mut Window, cx: &mut Context<Self>) -> bool {
        if self.lifecycle.quit_dispatched && self.production.shutdown_requested {
            return true;
        }
        self.request_exit(window, cx);
        false
    }
    pub(crate) fn request_exit(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        window.activate_window();
        cx.activate(true);
        if self.lifecycle.shutdown_waiting || self.production.shutdown_requested {
            self.message =
                "Cierre pendiente: esperando la finalización segura de las salidas.".into();
            cx.notify();
            return;
        }
        if self.lifecycle.confirmation_open {
            return;
        }
        let busy = self.production.engine.output_state() != 0
            || self.production.engine.scene_state().busy()
            || self.production.engine.overlay_animation_busy();
        if !busy {
            self.command(Command::RequestShutdown, "UI", cx);
            return;
        }
        self.lifecycle.confirmation_open = true;
        self.panel = None;
        self.picker = None;
        let revision = self.production.revision;
        let weak = cx.entity().downgrade();
        window.open_alert_dialog(cx, move |dialog, _, _| {
            let confirm = weak.clone();
            let closed = weak.clone();
            dialog.title("Finalizar producción y salir")
                .description("Se detendrán todas las salidas y se cancelará la transición activa. Motive permanecerá abierto hasta que terminen la grabación y las conexiones pendientes. Los cambios del proyecto no se guardan automáticamente.")
                .confirm()
                .ok_text("Finalizar y salir")
                .cancel_text("Seguir produciendo")
                .on_ok(move |_, _, cx| {
                    let _ = confirm.update(cx, |view, cx| {
                        if view.production.revision != revision {
                            view.message = "La producción cambió; vuelve a solicitar el cierre para revisar el estado actual.".into();
                            cx.notify();
                        } else {
                            view.command(Command::RequestShutdown, "UI", cx);
                        }
                    });
                    true
                })
                .on_close(move |_, _, cx| {
                    let _ = closed.update(cx, |view, cx| {
                        view.lifecycle.confirmation_open = false;
                        cx.notify();
                    });
                })
        });
        cx.notify();
    }
    pub(super) fn poll_lifecycle(&mut self, cx: &mut Context<Self>) -> bool {
        if crate::take_native_quit_request() {
            let window = self.lifecycle.window;
            let weak = cx.entity().downgrade();
            cx.defer(move |cx| {
                let _ = window.update(cx, |_, window, cx| {
                    let _ = weak.update(cx, |view, cx| view.request_exit(window, cx));
                });
            });
        }
        if self.production.shutdown_requested {
            if !self.lifecycle.diagnostics_saved {
                if self.production.persist_shutdown_diagnostics().is_err() {
                    eprintln!("{{\"code\":\"SHUTDOWN_DIAGNOSTIC_WRITE_FAILED\"}}");
                }
                self.lifecycle.diagnostics_saved = true;
            }
            if !self.lifecycle.quit_dispatched {
                if crate::authorize_native_quit() {
                    self.lifecycle.quit_dispatched = true;
                    cx.quit();
                } else {
                    self.message = "No se pudo completar el cierre nativo. Las salidas ya finalizaron; Motive permanece abierto.".into();
                    cx.notify();
                    return false;
                }
            }
            return true;
        }
        if self.lifecycle.shutdown_waiting {
            self.message = "Cierre pendiente: esperando salidas, conexiones e importaciones. La aplicación permanecerá abierta hasta terminar.".into();
        }
        false
    }
}
