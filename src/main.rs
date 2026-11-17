mod control;
mod core;
mod engine;
mod scene;

use core::Production;
use gpui_kit::*;
use serde_json::json;
mod ui;
use ui::Studio;

fn window_options(title: &str, w: f32, h: f32, cx: &App) -> WindowOptions {
    WindowOptions {
        window_bounds: Some(WindowBounds::Windowed(Bounds::centered(
            None,
            size(px(w), px(h)),
            cx,
        ))),
        titlebar: Some(TitlebarOptions {
            title: Some(title.to_owned().into()),
            ..Default::default()
        }),
        ..Default::default()
    }
}
fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).is_some_and(|a| a == "mcp") {
        return control::run_mcp();
    }
    if args.get(1).is_some_and(|a| a == "ctl") {
        let command = serde_json::from_str(
            args.get(2)
                .map(String::as_str)
                .unwrap_or(r#"{"op":"status"}"#),
        )?;
        let response = control::send(command, "cli");
        println!("{}", serde_json::to_string_pretty(&response)?);
        if response["ok"] != true {
            std::process::exit(1);
        }
        return Ok(());
    }
    application().with_assets(assets::AllAssets).run(|cx| {
        init(cx);
        ui::init(cx);
        let setup = (|| -> anyhow::Result<_> {
            let (server, requests) = control::Server::start()?;
            let production = Production::new()?;
            Ok((production, server, requests))
        })();
        match setup {
            Ok((production, server, requests)) => {
                open_window(ui::window_options(cx), cx, |window, cx| {
                    let view = cx.new(|cx| Studio::new(production, server, requests, window, cx));
                    let weak = view.downgrade();
                    window.on_window_should_close(cx, move |_, cx| {
                        let _ = weak.update(cx, |view, cx| {
                            if view.production.engine.output_state() != 0 {
                                view.message = "Finaliza la salida antes de cerrar.".into();
                                cx.notify();
                            } else {
                                cx.quit();
                            }
                        });
                        false
                    });
                    view
                })
                .expect("No se pudo abrir Motive");
                cx.activate(true);
            }
            Err(e) => {
                eprintln!(
                    "{}",
                    json!({"ok":false,"error":{"code":"STARTUP_FAILED","message":e.to_string()}})
                );
                cx.quit();
            }
        }
    });
    Ok(())
}
