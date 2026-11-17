mod control;
mod core;
mod diagnostics;
mod engine;
mod paths;
mod scene;

use core::Production;
use gpui_kit::*;
use serde_json::json;
mod ui;
use ui::Studio;

actions!(motive, [Quit]);
unsafe extern "C" {
    fn motive_lifecycle_install() -> bool;
    fn motive_lifecycle_take_quit_request() -> bool;
    fn motive_lifecycle_allow_quit() -> bool;
}
fn take_native_quit_request() -> bool {
    unsafe { motive_lifecycle_take_quit_request() }
}
fn authorize_native_quit() -> bool {
    unsafe { motive_lifecycle_allow_quit() }
}

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
    paths::init()?;
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
        cx.set_quit_mode(QuitMode::Explicit);
        cx.bind_keys([KeyBinding::new("cmd-q", Quit, None)]);
        // Install menus while the original framework delegate is still present.
        cx.set_menus([Menu::new("Motive").items([MenuItem::action("Salir de Motive", Quit)])]);
        if !unsafe { motive_lifecycle_install() } {
            eprintln!("{}", json!({"ok":false,"error":{"code":"LIFECYCLE_INIT_FAILED","message":"No se pudo instalar el cierre controlado"}}));
            // No Production/output exists yet; fail startup instead of exposing
            // an unguarded native Quit action to an active production.
            cx.quit();
            return;
        }
        let setup = (|| -> anyhow::Result<_> {
            let (server, requests) = control::Server::start()?;
            let production = Production::new()?;
            Ok((production, server, requests))
        })();
        match setup {
            Ok((production, server, requests)) => {
                let (studio_window, view) = open_window(ui::window_options(cx), cx, |window, cx| {
                    let view = cx.new(|cx| Studio::new(production, server, requests, window, cx));
                    let weak = view.downgrade();
                    window.on_window_should_close(cx, move |window, cx| {
                        weak.update(cx, |view, cx| view.close_requested(window, cx))
                            .unwrap_or(false)
                    });
                    view
                })
                .expect("No se pudo abrir Motive");
                let weak = view.downgrade();
                cx.on_action(move |_: &Quit, cx| {
                    let weak = weak.clone();
                    // Action dispatch may already borrow the active window.
                    cx.defer(move |cx| {
                        let _ = studio_window.update(cx, |_, window, cx| {
                            let _ = weak.update(cx, |view, cx| view.request_exit(window, cx));
                        });
                    });
                });
                cx.activate(true);
            }
            Err(e) => {
                eprintln!(
                    "{}",
                    json!({"ok":false,"error":{"code":"STARTUP_FAILED","message":e.to_string()}})
                );
                if authorize_native_quit() { cx.quit(); }
            }
        }
    });
    Ok(())
}
