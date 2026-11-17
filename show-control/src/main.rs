use motive_show_control::{
    model::{Error, Event},
    packs::{Capability, CreatorPack},
    runtime::Config,
    simulation,
};
use std::io::Read;

fn read(path: &str, max: u64) -> Result<String, Error> {
    let file = std::fs::File::open(path)
        .map_err(|_| Error::new("FILE_READ", "cannot open explicitly selected input file"))?;
    let mut result = String::new();
    file.take(max + 1)
        .read_to_string(&mut result)
        .map_err(|_| Error::new("FILE_READ", "input must be UTF-8"))?;
    if result.len() as u64 > max {
        return Err(Error::new("INPUT_TOO_LARGE", "input file exceeds limit"));
    }
    Ok(result)
}
fn json<T: serde::Serialize>(value: T) -> Result<serde_json::Value, Error> {
    serde_json::to_value(value).map_err(|_| Error::new("SERIALIZE", "result serialization failed"))
}
fn run(args: &[String]) -> Result<serde_json::Value, Error> {
    match args {
        [cmd] if cmd == "example-config" => json(simulation::demo_config()),
        [cmd, name] if cmd == "simulate" => json(simulation::scenario(name)?),
        [cmd, name, pack] if cmd == "simulate" => {
            let pack = CreatorPack::from_json(&read(pack, 262144)?)?;
            simulation::validate_pack_rules(&pack, &simulation::demo_config())?;
            json(simulation::scenario_with_snapshot(
                name,
                simulation::pack_snapshot(&pack)?,
            )?)
        }
        [cmd, path] if cmd == "validate-config" => {
            let c = Config::from_json(&read(path, 1048576)?)?;
            Ok(serde_json::json!({"valid":true,"rules":c.rules.len(),"simulation_only":true}))
        }
        [cmd, path] if cmd == "validate-event" => {
            let e = Event::from_json(&read(path, 65536)?)?;
            Ok(serde_json::json!({"valid":true,"kind":e.kind(),"simulated":e.simulated}))
        }
        [cmd, path] if cmd == "validate-pack" || cmd == "plan-pack" => {
            let pack = CreatorPack::from_json(&read(path, 262144)?)?;
            json(pack.plan(&Capability::h12_contracts())?)
        }
        [cmd, deck, pack, button] if cmd == "deck-press" => deck_press(deck, pack, button, false),
        [cmd, deck, pack, button, confirm] if cmd == "deck-press" && confirm == "--confirm" => {
            deck_press(deck, pack, button, true)
        }
        [cmd, config, events] if cmd == "run" => {
            let config = Config::from_json(&read(config, 1048576)?)?;
            let text = read(events, 1048576)?;
            let events = text
                .lines()
                .filter(|s| !s.trim().is_empty())
                .map(Event::from_json)
                .collect::<Result<Vec<_>, _>>()?;
            if events.len() > 1000 {
                return Err(Error::new("LIMIT", "at most 1000 events per run"));
            }
            json(simulation::run_events(
                "custom",
                config,
                events,
                simulation::fixture_snapshot(),
            )?)
        }
        [cmd, config, events, pack] if cmd == "run" => {
            let config = Config::from_json(&read(config, 1048576)?)?;
            let pack = CreatorPack::from_json(&read(pack, 262144)?)?;
            simulation::validate_pack_rules(&pack, &config)?;
            let events = read(events, 1048576)?
                .lines()
                .filter(|s| !s.trim().is_empty())
                .map(Event::from_json)
                .collect::<Result<Vec<_>, _>>()?;
            if events.len() > 1000 {
                return Err(Error::new("LIMIT", "at most 1000 events per run"));
            }
            json(simulation::run_events(
                "custom-pack",
                config,
                events,
                simulation::pack_snapshot(&pack)?,
            )?)
        }
        _ => Err(Error::new(
            "USAGE",
            "motive-show simulate <goal|donation|chat|burst> [pack.json] | example-config | validate-config <path> | validate-event <path> | validate-pack <path> | plan-pack <path> | run <config.json> <events.jsonl> [pack.json] | deck-press <deck.json> <pack.json> <button> [--confirm]",
        )),
    }
}
fn deck_press(
    deck: &str,
    pack: &str,
    button: &str,
    confirmed: bool,
) -> Result<serde_json::Value, Error> {
    use motive_show_control::deck::*;
    let mut deck = DeckRuntime::new(Deck::from_json(&read(deck, 65536)?)?)?;
    let pack = CreatorPack::from_json(&read(pack, 262144)?)?;
    let press = deck.press(button, 0, confirmed)?;
    let config = simulation::deck_actions(&press, &pack, &simulation::demo_config())?;
    let mut event = simulation::event(
        &format!("deck-{}", press.request_id),
        motive_show_control::model::Payload::ManualButtonPressed {
            button_id: button.into(),
        },
    );
    event.origin = "deck".into();
    let report = simulation::run_events(
        "deck",
        config,
        vec![event],
        simulation::pack_snapshot(&pack)?,
    )?;
    let error = report
        .admissions
        .iter()
        .find_map(|a| a.error.as_ref().map(|e| e.code.as_str()))
        .or({
            if report.jobs.is_empty() {
                Some("NO_MATCHING_RULE")
            } else {
                None
            }
        })
        .or_else(|| {
            report
                .jobs
                .iter()
                .filter(|j| j.state != motive_show_control::runtime::JobState::Simulated)
                .flat_map(|j| &j.records)
                .find_map(|r| r.code.as_deref())
        });
    deck.finish_simulation(press.request_id, 1, error)?;
    json(
        serde_json::json!({"press":press,"state":deck.state(button,1)?,"history":deck.history(),"simulation":report}),
    )
}
fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(value) => println!("{}", serde_json::to_string_pretty(&value).unwrap()),
        Err(error) => {
            eprintln!("{}", serde_json::json!({"ok":false,"error":error}));
            std::process::exit(1);
        }
    }
}
