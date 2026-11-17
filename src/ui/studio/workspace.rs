use super::*;
impl Render for Studio {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        self.sync_fields(window, cx);
        let p = Palette::new(self.dark);
        let status = self.production.status();
        self.sync_mixer_controls(&status, window, cx);
        let bounds = window.viewport_size();
        let width = f32::from(bounds.width);
        let height = f32::from(bounds.height);
        let rail = if width < 1200. { 232. } else { 296. };
        let main = width - rail;
        let pad = if width < 1200. { 18. } else { 24. };
        let stage_w = main - pad * 2.;
        let stage_h = (height - 52. - 56. - 210. - 24.).max(280.);
        let image_h = stage_h - 36. - 54.;
        let image_w = stage_w - 48.;
        let aspect = self.production.engine.width as f32 / self.production.engine.height as f32;
        let pw = image_w.min(image_h * aspect);
        let ph = pw / aspect;
        let scene = self
            .production
            .graph()
            .scene(&self.production.graph().active_scene)
            .unwrap();
        let vertical = self.production.project.variant == Variant::Vertical;
        let output_fault = status["recovery_sources"]
            .as_array()
            .is_some_and(|a| a.iter().any(|x| x == "output"));
        let video_fault = status["video"]["available"] != true;
        let video_busy = self.video_configuration_busy(&status);
        let issues = status["issues"].as_array().is_some_and(|a| !a.is_empty())
            || status["recovery_required"] == true
            || video_fault;
        let active = crate::core::output::OutputTarget::ALL
            .iter()
            .any(|target| status["outputs"][target.name()]["phase"] == "active");
        let encoder = self.output_encoder_summary(&status);
        div().id("studio").track_focus(&self.focus).on_key_down(cx.listener(Self::editor_key)).on_mouse_move(cx.listener(|v,e,_,cx|v.drag_move(e,cx))).on_mouse_up(MouseButton::Left,cx.listener(|v,_,_,cx|v.end_drag(cx))).on_mouse_up_out(MouseButton::Left,cx.listener(|v,_,_,cx|v.end_drag(cx))).size_full().flex().flex_col().bg(p.shell).text_color(p.ink).text_size(px(metrics::BODY))
            .child(self.header(&status,cx))
            .child(row().items_start().gap_0().flex_1().min_h_0()
                .child(col().w(px(main)).h_full().px(px(pad))
                    .child(row().h(px(56.)).flex_none().child(div().text_size(px(22.)).font_weight(FontWeight::SEMIBOLD).child(scene.name.clone()))
                        .child(row().gap_0().bg(p.sunken).rounded(px(5.)).ml(px(6.))
                            .child(self.action("horizontal","16:9",Command::SetVariant{variant:Variant::Horizontal},cx).icon(IconName::Monitor).selected(!vertical).disabled(video_busy))
                            .child(self.action("vertical","9:16",Command::SetVariant{variant:Variant::Vertical},cx).icon(IconName::Smartphone).selected(vertical).disabled(video_busy)))
                        .child(label(if video_fault { "Video no disponible".into() } else { format!("{} × {}   {} FPS",status["video"]["width"],status["video"]["height"],status["video"]["fps"]) },if video_fault { p.warn } else { p.muted })))
                    .child(col().flex_none().w(px(stage_w)).h(px(stage_h)).rounded(px(12.)).overflow_hidden().bg(p.stage).shadow_lg().border_t_2().border_color(if active {p.live}else{p.stage})
                        .child(div().relative().flex_1().flex().items_center().justify_center()
                            .child(self.canvas_view(pw,ph,cx))
                            .when(issues,|d|d.child(row().occlude().on_mouse_down(MouseButton::Left, |_, _, cx| cx.stop_propagation()).absolute().top(px(14.)).left(px(14.)).right(px(14.)).p(px(10.)).rounded(px(metrics::POPOVER_RADIUS)).bg(rgb(0x222429)).text_color(rgb(0xf1f2f4)).child(Icon::new(IconName::TriangleAlert).size(px(16.)).text_color(rgb(0xffb547))).child(col().flex_1().child(if video_fault {"Video no disponible"}else if output_fault {"Una salida requiere atención"}else{"Fuente no preparada"}).child(label(if video_fault {"Restaura el video en reposo; revisa el error en Preferencias."}else if output_fault {"Consulta el error y la recuperación de cada destino en Salidas."}else{"Revisa la captura y reconecta antes de continuar."},rgb(0xa2a7b0)))).child((if !video_fault && output_fault {self.output_details_action(cx)}else{self.action("recover-sources",if video_fault {"Restaurar video"}else{"Reconectar"},if video_fault {Command::ConfigureVideo{video:self.production.project.video.unwrap_or_default()}}else{Command::ReconnectSources},cx)}).disabled(video_fault && video_busy).bg(rgb(0xffffff)).text_color(rgb(0x16181d))))))
                        .child(row().h(px(36.)).flex_none().px(px(14.)).border_t_1().border_color(rgba(0xffffff13)).child(label("Ajustar",rgb(0xa2a7b0))).child(div().flex_1()).child(label(encoder,rgb(0xa2a7b0))).when(width>=1200.,|d|d.child(label(if video_fault { "Video no disponible".into() } else { format!("{} FPS configurados",status["video"]["fps"]) },rgb(0xa2a7b0))))))
                    .child(col().id("layers-scroll").overflow_y_scroll().flex_1().min_h_0().child(self.layers(cx))))
                .child(col().w(px(rail)).h_full().border_l_1().border_color(p.line).px(px(18.)).child(self.scenes(rail,&status,cx)).child(self.audio(&status,cx))))
            .child(row().h(px(24.)).flex_none().px(px(24.)).border_t_1().border_color(p.line).child(label(self.message.clone(),p.secondary).flex_1().overflow_hidden()).child(label(format!("Rev. {} · MCP local",self.production.revision),p.muted)))
    }
}
