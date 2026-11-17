//! Output policy on the existing Production owner; no multimedia worker here.
use super::{
    Production, data_dir,
    output::{OutputKind, OutputRegistry, OutputTarget, OutputVideo},
};
use std::{
    fs,
    time::{SystemTime, UNIX_EPOCH},
};

impl Production {
    pub(super) fn output_snapshot(&self) -> OutputRegistry {
        let mut outputs = self.outputs.clone();
        for target in OutputTarget::ALL {
            outputs
                .get_mut(target)
                .observe(self.engine.output_observation(target));
        }
        outputs
    }

    pub(super) fn poll_outputs(&mut self) {
        for target in OutputTarget::ALL {
            let observation = self.engine.output_observation(target);
            let was_failed = self.outputs.get(target).recovery_required;
            if self.outputs.get_mut(target).observe(observation) {
                self.revision += 1;
            }
            let output = self.outputs.get(target);
            if output.recovery_required && !was_failed {
                if !self.last_fault.iter().any(|code| code == "OUTPUT_FAILED") {
                    self.last_fault.push("OUTPUT_FAILED".into());
                }
                self.last_action = format!(
                    "OUTPUT_FAILED: {}; recuperación explícita por destino",
                    target.name()
                );
            }
            if output.cancel_requested && matches!(output.native_state, 1 | 4) {
                self.engine.stop_output_target(target);
            }
        }
    }

    pub(super) fn legacy_start_guard(&self) -> anyhow::Result<()> {
        self.idle()?;
        anyhow::ensure!(
            !self.output_snapshot().recovery_required(),
            "RECOVERY_REQUIRED"
        );
        Ok(())
    }

    pub(super) fn start_target(
        &mut self,
        target: OutputTarget,
        legacy_udp: bool,
    ) -> anyhow::Result<()> {
        if legacy_udp {
            self.idle()?;
            self.source_ready()?;
            self.output_snapshot().get(target).can_start()?;
        } else {
            self.preflight(target)?;
        }
        let selected = if legacy_udp {
            OutputTarget::Recording
        } else {
            target
        };
        let profile = self.profile(selected).clone();
        let profile_json = serde_json::to_string(&profile)?;
        let path = if target == OutputTarget::Recording {
            let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
            let path = data_dir()
                .join("recordings")
                .join(format!("motive-{stamp}.mkv"));
            fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)
                .map_err(|error| anyhow::anyhow!("OUTPUT_BAD_PATH: {}", error.kind()))?;
            Some(path.to_string_lossy().into_owned())
        } else {
            None
        };
        let kind = if legacy_udp {
            OutputKind::LocalStream
        } else if target == OutputTarget::Recording {
            OutputKind::Recording
        } else {
            OutputKind::Streaming
        };
        self.outputs.last_target = target;
        self.outputs.get_mut(target).begin(
            kind,
            profile,
            OutputVideo {
                width: self.engine.width,
                height: self.engine.height,
                fps: self.engine.fps,
            },
            path.clone(),
        );
        self.revision += 1;
        let result = if legacy_udp {
            self.engine.start_output("", true, &profile_json)
        } else if target == OutputTarget::Recording {
            self.engine.start_output(
                path.as_deref().expect("reserved recording path"),
                false,
                &profile_json,
            )
        } else {
            self.engine.start_stream(
                &self
                    .stream_endpoint
                    .as_ref()
                    .expect("validated local endpoint")
                    .url(),
                &profile_json,
                self.stream_credential.as_deref(),
            )
        };
        self.outputs
            .get_mut(target)
            .observe(self.engine.output_observation(target));
        if let Err(error) = result {
            let output = self.outputs.get_mut(target);
            if output.failure.is_none() {
                output.fail_start(&error);
            }
            // Only the newly reserved empty file is disposable. A partial MKV
            // is evidence, and a live native worker still owns its destination.
            if !output.native_busy
                && let Some(path) = path
                && fs::metadata(&path).is_ok_and(|metadata| metadata.len() == 0)
            {
                let _ = fs::remove_file(path);
            }
            return Err(error);
        }
        Ok(())
    }

    pub(super) fn stop_target(
        &mut self,
        target: OutputTarget,
        deferred: bool,
    ) -> anyhow::Result<()> {
        let observation = self.engine.output_observation(target);
        self.outputs.get_mut(target).observe(observation);
        let output = self.outputs.get_mut(target);
        anyhow::ensure!(
            deferred || output.native_state != 3,
            "OUTPUT_CONNECTING: usa cancel_output_target y espera la barrera de workers"
        );
        output.request_cancel();
        self.engine.stop_output_target(target);
        Ok(())
    }

    pub(super) fn cancel_all_outputs(&mut self) {
        for target in OutputTarget::ALL {
            self.outputs
                .get_mut(target)
                .observe(self.engine.output_observation(target));
            self.outputs.get_mut(target).request_cancel();
        }
        self.engine.stop_output();
    }

    pub(super) fn recover_target(&mut self, target: OutputTarget) -> anyhow::Result<()> {
        let observation = self.engine.output_observation(target);
        self.outputs.get_mut(target).observe(observation);
        anyhow::ensure!(!self.outputs.get(target).native_busy, "OUTPUT_BUSY");
        self.engine.reset_output_target(target)?;
        self.outputs.get_mut(target).recover()?;
        Ok(())
    }
}
