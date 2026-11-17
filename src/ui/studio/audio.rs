use super::*;
impl Studio {
    pub(super) fn audio(&self, status: &Value, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let peak = status["stats"]["audio_peak"]
            .as_f64()
            .unwrap_or(0.)
            .clamp(0., 1.);
        let db = if peak > 0. { 20. * peak.log10() } else { -60. };
        let bars = ((db + 60.) / 60. * 48.).clamp(0., 48.) as usize;
        let audio = &self.production.project.audio;
        let name = if audio == "tone" {
            "Tono de prueba".to_owned()
        } else if audio == "none" {
            "Sin entrada".to_owned()
        } else {
            self.devices["audio"]
                .as_array()
                .and_then(|a| a.iter().find(|x| x["id"].as_str() == Some(audio)))
                .and_then(|x| x["name"].as_str())
                .unwrap_or("Micrófono físico")
                .to_owned()
        };
        col()
            .flex_none()
            .border_t_1()
            .border_color(p.line)
            .pt(px(12.))
            .pb(px(20.))
            .gap(px(10.))
            .child(
                row()
                    .child(
                        div()
                            .flex_1()
                            .font_weight(FontWeight::SEMIBOLD)
                            .child("Audio"),
                    )
                    .child(self.panel_button("audio", "", IconName::SlidersHorizontal, cx)),
            )
            .child(
                row()
                    .child(
                        Icon::new(IconName::Mic)
                            .size(px(16.))
                            .text_color(p.secondary),
                    )
                    .child(
                        div()
                            .flex_1()
                            .overflow_hidden()
                            .text_size(px(12.))
                            .child(name),
                    )
                    .child(label(
                        if peak > 0. {
                            format!("{db:.1} dBFS")
                        } else {
                            "−∞ dBFS".into()
                        },
                        p.secondary,
                    )),
            )
            .child(row().gap(px(1.)).children((0..48).map(|i| {
                div().flex_1().h(px(5.)).bg(if i < bars {
                    if i > 43 {
                        p.live
                    } else if i > 36 {
                        p.warn
                    } else {
                        p.ready
                    }
                } else {
                    p.sunken
                })
            })))
            .child(
                row().justify_between().children(
                    ["−60", "−30", "−12", "0"].map(|x| label(x, p.muted).text_size(px(10.))),
                ),
            )
            .child(label("Nivel pico real · entrada global", p.secondary))
            .child(label("Ganancia y mezcla: próximo hito", p.muted).text_size(px(11.)))
    }
}
