use motive_creator_runtime_lab::{
    Error,
    model::Snapshot,
    persistence::Store,
    planner::InsertRequest,
    receipts::{Phase, StrictOwnerModel},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::io::{self, Read};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    snapshot: Snapshot,
    #[serde(default)]
    insertions: Vec<InsertRequest>,
    #[serde(default)]
    operation: Operation,
    #[serde(default)]
    store: Option<Value>,
    #[serde(default)]
    verified_packages: std::collections::BTreeMap<String, motive_show_control::packs::CreatorPack>,
}
#[derive(Default, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Operation {
    #[default]
    Simulate,
    AssessRestore,
}
fn run(bytes: &[u8]) -> Result<Value, Error> {
    let request: Request = serde_json::from_slice(bytes)
        .map_err(|_| Error::new("REQUEST_SCHEMA", "Invalid offline request"))?;
    if request.operation == Operation::AssessRestore {
        if !request.insertions.is_empty() {
            return Err(Error::new(
                "REQUEST_SCHEMA",
                "Restore assessment cannot insert elements",
            ));
        }
        let value = request
            .store
            .ok_or_else(|| Error::new("STORE_REQUIRED", "Sidecar required"))?;
        let store = Store::parse(
            &serde_json::to_vec(&value).map_err(|_| Error::new("STORE_SCHEMA", "Invalid state"))?,
        )?;
        let report = store.assess_restore(&request.verified_packages, &request.snapshot)?;
        return Ok(
            json!({"status":if report.issues.is_empty(){"PASS"}else{"PARTIAL"},"scope":"offline_restore_assessment","report":report,"production_connected":false}),
        );
    }
    if request.store.is_some() || !request.verified_packages.is_empty() {
        return Err(Error::new("REQUEST_SCHEMA", "Unexpected restore data"));
    }
    if request.insertions.is_empty() || request.insertions.len() > 16 {
        return Err(Error::new(
            "REQUEST_LIMIT",
            "Expected 1–16 offline insertions",
        ));
    }
    let mut owner = StrictOwnerModel::new(request.snapshot)?;
    let mut installations = vec![];
    let mut stopped_on_error = None;
    for insertion in request.insertions {
        let attempted = owner
            .review(insertion)
            .and_then(|review| owner.install(review));
        match attempted {
            Ok(installation) => {
                let complete = installation.phase == Phase::InstalledInModel;
                installations.push(installation);
                if !complete {
                    break; // No implicit continuation after partial/uncertain work.
                }
            }
            Err(error) if installations.is_empty() => return Err(error),
            Err(error) => {
                // Earlier insertions already changed the model. Retain their
                // journal and graph even when a later review was rejected.
                stopped_on_error = Some(error);
                break;
            }
        }
    }
    let store = Store::capture(&installations, &owner.snapshot)?;
    let complete = stopped_on_error.is_none()
        && installations
            .iter()
            .all(|i| i.phase == Phase::InstalledInModel);
    Ok(
        json!({"status":if complete {"PASS"} else {"PARTIAL"},"scope":"strict_offline_owner_model","production_connected":false,"native_render_verified":false,
        "show_control_armed":false,"installations":installations,"snapshot_budget":owner.snapshot.budget(),"snapshot":owner.snapshot,"store":store,"stopped_on_error":stopped_on_error}),
    )
}
fn main() {
    let mut bytes = vec![];
    let result = match io::stdin().take(4_194_305).read_to_end(&mut bytes) {
        Ok(_) if bytes.len() <= 4_194_304 => run(&bytes),
        _ => Err(Error::new("REQUEST_SIZE", "Request exceeds 4 MiB")),
    };
    match result {
        Ok(value) => {
            println!("{value}");
            if value["status"] == "PARTIAL" {
                std::process::exit(1);
            }
        }
        Err(e) => {
            println!("{}", json!({"status":"FAIL","error":e}));
            std::process::exit(1);
        }
    }
}
