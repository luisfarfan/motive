use gpui_kit::*;
use std::time::Duration;
pub(super) struct Pattern {
    tick: u64,
}
impl Pattern {
    pub(super) fn new(cx: &mut Context<Self>) -> Self {
        cx.spawn(async move |this, cx| {
            loop {
                cx.background_executor()
                    .timer(Duration::from_millis(100))
                    .await;
                if this
                    .update(cx, |v, cx| {
                        v.tick += 1;
                        cx.notify();
                    })
                    .is_err()
                {
                    break;
                }
            }
        })
        .detach();
        Self { tick: 0 }
    }
}
impl Render for Pattern {
    fn render(&mut self, _: &mut Window, _: &mut Context<Self>) -> impl IntoElement {
        div()
            .size_full()
            .flex()
            .flex_col()
            .p_8()
            .gap_6()
            .bg(rgb(0x162c40))
            .text_color(rgb(0xffffff))
            .child(div().text_3xl().child("MOTIVE / FUENTE CONTROLADA"))
            .child("Esta es una ventana nativa independiente. Captúrala desde el estudio.")
            .child(format!("Contenido de prueba propio · tick {}", self.tick))
            .child(div().flex().gap_4().children((0..5).map(|i| {
                div().w(px(76.)).h(px(76.)).bg(if self.tick % 5 == i {
                    rgb(0x64e4c1)
                } else {
                    rgb(0x315475)
                })
            })))
    }
}
