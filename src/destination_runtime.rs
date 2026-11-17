//! Destination policy on the one Production owner. Public control can select
//! an approved ID, but only a local typed review can approve or start it.
use super::{
    Production,
    destinations::*,
    output::{OutputKind, OutputTarget, OutputVideo},
};
use serde_json::{Value, json};
use std::{
    fs,
    os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt},
    path::PathBuf,
    time::Instant,
};

struct Enrollment {
    request_id: u64,
    destination_id: String,
    binding: String,
    revision: u64,
    destination: DestinationSpec,
}

struct PendingEnrollment {
    job: Enrollment,
    result: crate::engine::CredentialEnrollmentResult,
    last_attempt: Option<Instant>,
}
pub(super) struct State {
    registry: DestinationRegistry,
    store_path: PathBuf,
    receipt_path: PathBuf,
    receipts: CredentialReceipts,
    load_error: Option<&'static str>,
    started: Instant,
    next_request: u64,
    enrollment: Option<Enrollment>,
    pending_enrollment: Option<PendingEnrollment>,
    last_enrollment: Value,
}
impl State {
    pub(super) fn new() -> Self {
        Self::from_directory(super::data_dir().join("streaming"))
    }
    fn from_directory(directory: PathBuf) -> Self {
        let path = directory.join("destinations.json");
        let receipt_path = directory.join("credential-reconciliation.json");
        let load = (|| -> anyhow::Result<DestinationStore> {
            if !directory.exists() {
                fs::DirBuilder::new().mode(0o700).create(&directory)?;
            }
            let metadata = directory.symlink_metadata()?;
            anyhow::ensure!(
                metadata.is_dir()
                    && metadata.uid() == unsafe { libc::geteuid() }
                    && metadata.permissions().mode() & 0o777 == 0o700,
                "INVALID_DESTINATION_DIRECTORY"
            );
            match path.symlink_metadata() {
                Ok(_) => DestinationStore::load(&path),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    Ok(DestinationStore::default())
                }
                Err(error) => Err(error.into()),
            }
        })();
        let mut load_error = load.as_ref().err().map(|_| "DESTINATION_STORE_UNAVAILABLE");
        let receipt_load = match receipt_path.symlink_metadata() {
            Ok(_) => CredentialReceipts::load(&receipt_path),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                Ok(CredentialReceipts::default())
            }
            Err(error) => Err(error.into()),
        };
        if receipt_load.is_err() {
            load_error = Some("CREDENTIAL_RECONCILIATION_STORE_UNAVAILABLE");
        }
        let receipts = receipt_load.unwrap_or_default();
        let registry = DestinationRegistry::new(load.unwrap_or_default())
            .expect("validated destination store");
        let last_enrollment = receipts
            .receipts
            .last()
            .map(|receipt| {
                let attached = registry.receipt_attached(receipt);
                json!({"request_id":receipt.request_id,"phase":receipt.phase,
                "credential_ref":receipt.credential_ref,"destination_id":receipt.destination.id,
                "binding":receipt.binding,"attached":attached,
                "reconciliation_required":!attached,"restored":true,"terminal":true})
            })
            .unwrap_or(Value::Null);
        let next_request = receipts
            .receipts
            .iter()
            .map(|r| r.request_id)
            .max()
            .unwrap_or(0)
            .saturating_add(1);
        Self {
            registry,
            store_path: path,
            receipt_path,
            receipts,
            load_error,
            started: Instant::now(),
            next_request,
            enrollment: None,
            pending_enrollment: None,
            last_enrollment,
        }
    }
    fn now(&self) -> u64 {
        self.started.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
    fn available(&self) -> anyhow::Result<()> {
        anyhow::ensure!(self.load_error.is_none(), "DESTINATION_STORE_UNAVAILABLE");
        Ok(())
    }
    fn transaction<T>(
        &mut self,
        edit: impl FnOnce(&mut DestinationRegistry) -> anyhow::Result<T>,
    ) -> anyhow::Result<T> {
        self.transaction_with(edit, |store, path| store.save(path))
    }
    fn transaction_with<T>(
        &mut self,
        edit: impl FnOnce(&mut DestinationRegistry) -> anyhow::Result<T>,
        save: impl FnOnce(&DestinationStore, &std::path::Path) -> anyhow::Result<()>,
    ) -> anyhow::Result<T> {
        self.available()?;
        let mut candidate = self.registry.staged();
        let result = edit(&mut candidate)?;
        if save(candidate.store(), &self.store_path).is_err() {
            self.registry.suspend();
            self.load_error = Some("DESTINATION_STORE_WRITE_FAILED");
            anyhow::bail!("DESTINATION_STORE_WRITE_FAILED");
        }
        self.registry = candidate;
        Ok(result)
    }
    fn pending_receipts(&self) -> impl Iterator<Item = &CredentialReceipt> {
        self.receipts
            .receipts
            .iter()
            .filter(|r| !self.registry.receipt_attached(r))
    }
    fn receipt_candidate(&self, receipt: CredentialReceipt) -> anyhow::Result<CredentialReceipts> {
        let mut candidate = CredentialReceipts {
            version: 1,
            receipts: self.pending_receipts().cloned().collect(),
        };
        candidate.receipts.push(receipt);
        candidate.validate()?;
        Ok(candidate)
    }
}

impl Production {
    pub fn destinations_status(&self) -> Value {
        json!({"version":1,"destinations":self.destinations.registry.list(),
            "selected":self.destinations.registry.selected(),"load_error":self.destinations.load_error,
            "credential_busy":self.destination_credential_busy(),
            "enrollment":self.destinations.last_enrollment,"local_start_required":true,
            "reconciliation_pending":self.destinations.pending_receipts().collect::<Vec<_>>(),
            "automatic_start":false,"external_delivery_verified":false})
    }
    /// Also guards shutdown while a consumed native result awaits its durable receipt.
    pub fn destination_credential_busy(&self) -> bool {
        self.engine.destination_credential_busy()
            || self.destinations.enrollment.is_some()
            || self.destinations.pending_enrollment.is_some()
    }
    pub fn external_destination_selected(&self) -> bool {
        self.destinations.registry.selected().is_some()
    }
    fn destination_admit_edit(&self) -> anyhow::Result<()> {
        self.destinations.available()?;
        anyhow::ensure!(
            !self.shutdown_pending && !self.shutdown_requested,
            "SHUTDOWN_PENDING"
        );
        anyhow::ensure!(!self.output_snapshot().streaming.native_busy, "OUTPUT_BUSY");
        anyhow::ensure!(
            !self.destination_credential_busy(),
            "CREDENTIAL_ENROLLMENT_BUSY"
        );
        Ok(())
    }
    pub fn select_approved_destination(&mut self, id: Option<&str>) -> anyhow::Result<()> {
        self.destination_admit_edit()?;
        if let Some(id) = id {
            self.destinations.registry.select_approved(id)?;
        } else {
            self.destinations.registry.clear_selection()?;
        }
        self.bump_external_revision();
        Ok(())
    }
    pub fn save_destination_local(
        &mut self,
        spec: DestinationSpec,
        revision: u64,
    ) -> anyhow::Result<LocalDestinationReview> {
        self.poll_health();
        self.destination_admit_edit()?;
        anyhow::ensure!(revision == self.revision, "STALE_DESTINATION_FORM");
        let id = spec.id.clone();
        self.destinations
            .transaction(|registry| registry.upsert_local(spec))?;
        self.bump_external_revision();
        self.destinations.registry.review_local(&id)
    }
    pub fn review_destination_local(&self, id: &str) -> anyhow::Result<LocalDestinationReview> {
        self.destination_admit_edit()?;
        self.destinations.registry.review_local(id)
    }
    pub fn approve_destination_local(
        &mut self,
        review: LocalDestinationReview,
    ) -> anyhow::Result<()> {
        self.destination_admit_edit()?;
        self.destinations
            .transaction(|registry| registry.approve_local(review))?;
        self.bump_external_revision();
        Ok(())
    }
    pub fn remove_destination_local(&mut self, id: &str, revision: u64) -> anyhow::Result<()> {
        self.poll_health();
        self.destination_admit_edit()?;
        anyhow::ensure!(revision == self.revision, "STALE_DESTINATION_FORM");
        self.destinations
            .transaction(|registry| registry.remove_local(id))?;
        self.bump_external_revision();
        Ok(())
    }
    fn destination_credential_check(&self, destination: &DestinationSpec) -> CredentialCheck {
        let Some(reference) = &destination.credential_ref else {
            return CredentialCheck::Missing;
        };
        let Ok(binding) = destination.credential_binding() else {
            return CredentialCheck::BindingMismatch;
        };
        match self
            .engine
            .destination_credential_status(reference, &binding)
        {
            0 => CredentialCheck::Available,
            1 => CredentialCheck::Missing,
            2 => CredentialCheck::AccessDenied,
            4 | 5 => CredentialCheck::BindingMismatch,
            _ => CredentialCheck::Unavailable,
        }
    }
    pub(super) fn check_selected_destination(&self) -> anyhow::Result<()> {
        self.destinations.available()?;
        let id = self
            .destinations
            .registry
            .selected()
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_NOT_SELECTED"))?;
        let destination = self.destinations.registry.approved(id)?;
        let check = self.destination_credential_check(destination);
        anyhow::ensure!(
            check == CredentialCheck::Available,
            "{}",
            match check {
                CredentialCheck::Missing => "CREDENTIAL_MISSING",
                CredentialCheck::AccessDenied => "CREDENTIAL_ACCESS_DENIED",
                CredentialCheck::BindingMismatch => "CREDENTIAL_BINDING_MISMATCH",
                _ => "KEYCHAIN_UNAVAILABLE",
            }
        );
        Ok(())
    }
    pub fn preflight_destination(&mut self, id: &str) -> anyhow::Result<DestinationPreflight> {
        self.destination_admit_edit()?;
        let spec = self.destinations.registry.approved(id)?;
        let check = self.destination_credential_check(spec);
        self.destinations.registry.preflight(id, check)
    }
    pub fn prepare_destination_start_local(&mut self) -> anyhow::Result<LocalStartRequest> {
        self.poll_health();
        self.destination_admit_edit()?;
        let id = self
            .destinations
            .registry
            .selected()
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_NOT_SELECTED"))?
            .to_owned();
        self.preflight_destination(&id)?;
        self.preflight(OutputTarget::Streaming)?;
        self.destinations.registry.prepare_local_start(
            OwnerRevision {
                pid: std::process::id(),
                revision: self.revision,
            },
            self.profile(OutputTarget::Streaming).clone(),
            self.destinations.now(),
        )
    }
    pub fn start_destination_local(&mut self, request: LocalStartRequest) -> anyhow::Result<()> {
        self.poll_health();
        self.destination_admit_edit()?;
        self.preflight(OutputTarget::Streaming)?;
        let owner = OwnerRevision {
            pid: std::process::id(),
            revision: self.revision,
        };
        let profile = self.profile(OutputTarget::Streaming).clone();
        let check = self.destination_credential_check(request.destination());
        let grant = self.destinations.registry.confirm_local_start(
            request,
            owner,
            &profile,
            self.destinations.now(),
        )?;
        let authority = self.destinations.registry.consume_local_start(
            grant,
            owner,
            &profile,
            self.destinations.now(),
            check,
        )?;
        let (destination, profile) = authority.into_parts();
        let profile_json = serde_json::to_string(&profile)?;
        let binding = destination.credential_binding()?;
        self.outputs.last_target = OutputTarget::Streaming;
        self.outputs.streaming.begin(
            OutputKind::Streaming,
            profile,
            OutputVideo {
                width: self.engine.width,
                height: self.engine.height,
                fps: self.engine.fps,
            },
            None,
        );
        self.bump_external_revision();
        let result = self.engine.start_approved_stream(
            &destination.server_url(),
            &profile_json,
            destination
                .credential_ref
                .as_deref()
                .expect("fresh credential check"),
            &binding,
        );
        self.outputs
            .streaming
            .observe(self.engine.output_observation(OutputTarget::Streaming));
        if let Err(error) = result {
            if self.outputs.streaming.failure.is_none() {
                self.outputs.streaming.fail_start(&error);
            }
            return Err(error);
        }
        self.last_action = format!("Transmisión aprobada: {}", destination.name);
        Ok(())
    }
    /// The pointer is obtained from this GPUI window's AppKit view, on the owner.
    /// No key value is accepted by this API.
    ///
    /// # Safety
    /// `view` must be the AppKit NSView pointer of the live owner window.
    pub unsafe fn begin_destination_credential_local(
        &mut self,
        view: *mut std::ffi::c_void,
        id: &str,
        revision: u64,
    ) -> anyhow::Result<()> {
        self.poll_health();
        self.destination_admit_edit()?;
        anyhow::ensure!(revision == self.revision, "STALE_DESTINATION_FORM");
        anyhow::ensure!(
            self.destinations.enrollment.is_none(),
            "CREDENTIAL_ENROLLMENT_BUSY"
        );
        anyhow::ensure!(
            CredentialReceipts {
                version: 1,
                receipts: self.destinations.pending_receipts().cloned().collect()
            }
            .has_capacity(),
            "CREDENTIAL_RECONCILIATION_CAPACITY"
        );
        let review = self.destinations.registry.review_local(id)?;
        let mut destination = review.destination().clone();
        destination.credential_ref = None;
        let binding = review.destination().credential_binding()?;
        let metadata = json!({"name":review.destination().name,"binding":binding}).to_string();
        let request_id = self.destinations.next_request;
        self.destinations.next_request = request_id
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("CREDENTIAL_REQUEST_EXHAUSTED"))?;
        unsafe {
            self.engine
                .begin_destination_credential(view, &metadata, request_id)?;
        }
        self.destinations.enrollment = Some(Enrollment {
            request_id,
            destination_id: id.into(),
            binding,
            revision,
            destination,
        });
        self.destinations.last_enrollment =
            json!({"request_id":request_id,"phase":"awaiting_user"});
        Ok(())
    }
    pub fn cancel_destination_credential(&mut self) {
        if let Some(job) = &self.destinations.enrollment {
            self.engine.cancel_destination_credential(job.request_id);
        }
        if let Some(pending) = &mut self.destinations.pending_enrollment {
            pending.result.cancel_requested = true;
            pending.result.phase = "stored_after_cancel";
            self.destinations.last_enrollment["phase"] = json!("stored_after_cancel");
            self.destinations.last_enrollment["cancel_requested"] = json!(true);
        }
    }
    pub(super) fn poll_destination_credential(&mut self) {
        if self.destinations.pending_enrollment.is_none() {
            let Some(job) = &self.destinations.enrollment else {
                return;
            };
            let Some(result) = self.engine.poll_destination_credential(job.request_id) else {
                return;
            };
            self.destinations.last_enrollment = serde_json::to_value(&result).unwrap();
            if !result.terminal {
                return;
            }
            let job = self.destinations.enrollment.take().unwrap();
            if result.credential_ref.is_none() {
                self.destinations.last_enrollment["attached"] = json!(false);
                self.bump_external_revision();
                return;
            }
            self.destinations.pending_enrollment = Some(PendingEnrollment {
                job,
                result,
                last_attempt: None,
            });
        }
        // The native terminal result has been consumed, but stays owned here
        // until its receipt is durable. Poll retries after disk recovery; busy
        // blocks a new sheet and clean shutdown throughout that interval.
        let pending = self.destinations.pending_enrollment.as_mut().unwrap();
        if pending
            .last_attempt
            .is_some_and(|last| last.elapsed().as_secs() < 1)
        {
            return;
        }
        pending.last_attempt = Some(Instant::now());
        let receipt = CredentialReceipt {
            request_id: pending.job.request_id,
            owner_pid: std::process::id(),
            requested_revision: pending.job.revision,
            destination: pending.job.destination.clone(),
            binding: pending.job.binding.clone(),
            phase: if pending.result.phase == "stored_after_cancel" {
                StoredCredentialPhase::StoredAfterCancel
            } else {
                StoredCredentialPhase::Stored
            },
            credential_ref: pending.result.credential_ref.clone().unwrap(),
        };
        let saved = self
            .destinations
            .receipt_candidate(receipt)
            .and_then(|candidate| {
                candidate.save(&self.destinations.receipt_path)?;
                Ok(candidate)
            });
        match saved {
            Ok(receipts) => self.destinations.receipts = receipts,
            Err(_) => {
                self.destinations.last_enrollment["persistence_error"] =
                    json!("CREDENTIAL_RECEIPT_WRITE_FAILED");
                self.destinations.last_enrollment["reconciliation_required"] = json!(true);
                self.destinations.last_enrollment["shutdown_blocked"] = json!(true);
                return;
            }
        }
        let PendingEnrollment { job, result, .. } =
            self.destinations.pending_enrollment.take().unwrap();
        self.destinations.last_enrollment = serde_json::to_value(&result).unwrap();
        let attached = if result.phase == "stored"
            && !self.shutdown_pending
            && !self.shutdown_requested
            && self.revision == job.revision
        {
            self.destinations.transaction(|registry| {
                registry.associate_credential_local(
                    &job.destination_id,
                    &job.binding,
                    result.credential_ref.clone().unwrap(),
                )
            })
        } else {
            Err(anyhow::anyhow!("CREDENTIAL_RECONCILIATION_REQUIRED"))
        };
        self.destinations.last_enrollment["attached"] = json!(attached.is_ok());
        self.destinations.last_enrollment["reconciliation_required"] = json!(attached.is_err());
        self.destinations.last_enrollment["receipt_persisted"] = json!(true);
        if attached.is_err() && self.destinations.load_error.is_some() {
            self.destinations.last_enrollment["persistence_error"] =
                json!(self.destinations.load_error);
        }
        self.bump_external_revision();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(1);
    const REFERENCE: &str = "kc_12345678-1234-1234-1234-123456789abc";
    struct TestDirectory(PathBuf);
    impl TestDirectory {
        fn new() -> Self {
            Self(std::env::temp_dir().join(format!(
                "motive-destination-runtime-{}-{}",
                std::process::id(),
                NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed)
            )))
        }
    }
    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn spec() -> DestinationSpec {
        DestinationSpec {
            id: "private-test".into(),
            name: "Private test".into(),
            protocol: DestinationProtocol::Rtmps,
            host: "stream.example.com".to_owned().try_into().unwrap(),
            port: 443,
            application: "/live".to_owned().try_into().unwrap(),
            credential_ref: None,
        }
    }
    fn initial(directory: &TestDirectory) -> State {
        let mut state = State::from_directory(directory.0.clone());
        state
            .transaction(|registry| registry.upsert_local(spec()))
            .unwrap();
        state
    }
    fn receipt() -> CredentialReceipt {
        CredentialReceipt {
            request_id: 17,
            owner_pid: 71,
            requested_revision: 12,
            destination: spec(),
            binding: spec().credential_binding().unwrap(),
            phase: StoredCredentialPhase::StoredAfterCancel,
            credential_ref: REFERENCE.into(),
        }
    }
    #[test]
    fn failed_approval_never_changes_owner_and_blocks_further_authority() {
        for after_rename in [false, true] {
            let directory = TestDirectory::new();
            let mut state = initial(&directory);
            let review = state.registry.review_local("private-test").unwrap();
            assert!(
                state
                    .transaction_with(
                        |r| r.approve_local(review),
                        |store, path| {
                            // Deterministic injection on each side of the durability boundary.
                            if after_rename {
                                store.save(path)?;
                            }
                            anyhow::bail!("injected storage failure")
                        }
                    )
                    .is_err()
            );
            assert_eq!(state.registry.list()[0].approval, ApprovalState::Draft);
            assert!(state.registry.selected().is_none());
            assert_eq!(state.load_error, Some("DESTINATION_STORE_WRITE_FAILED"));
            assert!(state.available().is_err());
            let disk = DestinationStore::load(&state.store_path).unwrap();
            assert_eq!(
                disk.destinations[0].approval,
                if after_rename {
                    ApprovalState::Approved
                } else {
                    ApprovalState::Draft
                }
            );
            let reopened = State::from_directory(directory.0.clone());
            assert!(reopened.registry.selected().is_none());
            assert_eq!(
                reopened.registry.list()[0].validation,
                ValidationState::Unchecked
            );
        }
    }
    #[test]
    fn failed_association_leaves_exact_old_reference_in_memory() {
        let directory = TestDirectory::new();
        let mut state = initial(&directory);
        let binding = spec().credential_binding().unwrap();
        assert!(
            state
                .transaction_with(
                    |r| r.associate_credential_local("private-test", &binding, REFERENCE.into()),
                    |_, _| anyhow::bail!("disk full")
                )
                .is_err()
        );
        assert!(
            state.registry.list()[0]
                .destination
                .credential_ref
                .is_none()
        );
    }
    #[test]
    fn invalid_edit_does_not_poison_a_valid_store() {
        let directory = TestDirectory::new();
        let mut state = initial(&directory);
        assert!(state.transaction(|r| r.remove_local("missing")).is_err());
        assert!(state.available().is_ok());
        let review = state.registry.review_local("private-test").unwrap();
        state.transaction(|r| r.approve_local(review)).unwrap();
        assert_eq!(
            DestinationStore::load(&state.store_path)
                .unwrap()
                .destinations[0]
                .approval,
            ApprovalState::Approved
        );
    }
    #[test]
    fn cancelled_receipt_survives_reopen_with_exact_binding_and_no_automatic_attach() {
        let directory = TestDirectory::new();
        let state = initial(&directory);
        let receipts = state.receipt_candidate(receipt()).unwrap();
        receipts.save(&state.receipt_path).unwrap();
        let reopened = State::from_directory(directory.0.clone());
        assert_eq!(reopened.receipts.receipts, vec![receipt()]);
        assert_eq!(reopened.last_enrollment["phase"], "stored_after_cancel");
        assert_eq!(reopened.last_enrollment["credential_ref"], REFERENCE);
        assert_eq!(reopened.last_enrollment["reconciliation_required"], true);
        assert_eq!(reopened.last_enrollment["restored"], true);
        assert_eq!(reopened.next_request, 18);
        assert!(
            reopened.registry.list()[0]
                .destination
                .credential_ref
                .is_none()
        );
        assert!(reopened.registry.selected().is_none());
        let metadata = fs::metadata(&state.receipt_path).unwrap();
        assert_eq!(metadata.permissions().mode() & 0o777, 0o600);
    }
    #[test]
    fn receipt_write_failure_can_retry_and_never_discards_earlier_unresolved_entries() {
        let directory = TestDirectory::new();
        let mut state = initial(&directory);
        state.receipts = state.receipt_candidate(receipt()).unwrap();
        state.receipts.save(&state.receipt_path).unwrap();
        let mut next = receipt();
        next.request_id += 1;
        let candidate = state.receipt_candidate(next.clone()).unwrap();
        fs::set_permissions(&state.receipt_path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(candidate.save(&state.receipt_path).is_err());
        assert_eq!(state.receipts.receipts, vec![receipt()]);
        fs::set_permissions(&state.receipt_path, fs::Permissions::from_mode(0o600)).unwrap();
        candidate.save(&state.receipt_path).unwrap();
        assert_eq!(
            CredentialReceipts::load(&state.receipt_path)
                .unwrap()
                .receipts,
            vec![receipt(), next]
        );
    }
    #[test]
    fn receipt_binding_mismatch_and_unknown_fields_fail_closed_on_load() {
        let directory = TestDirectory::new();
        let state = initial(&directory);
        let receipts = state.receipt_candidate(receipt()).unwrap();
        receipts.save(&state.receipt_path).unwrap();
        let mut invalid = receipts.clone();
        invalid.receipts[0].destination.port = 8443;
        assert!(invalid.save(&state.receipt_path).is_err());
        let mut value = serde_json::to_value(receipts).unwrap();
        value["receipts"][0]["secret"] = json!("forbidden");
        fs::write(&state.receipt_path, serde_json::to_vec(&value).unwrap()).unwrap();
        let reopened = State::from_directory(directory.0.clone());
        assert_eq!(
            reopened.load_error,
            Some("CREDENTIAL_RECONCILIATION_STORE_UNAVAILABLE")
        );
        assert!(reopened.available().is_err());
    }
}
