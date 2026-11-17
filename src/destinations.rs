//! Approved RTMPS destinations. Local review and start grants are not Commands.
//! No network IO, Keychain plaintext, implicit selection or automatic start here.
use super::output::{OutputProfile, valid_credential_ref};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{IpAddr, Ipv4Addr};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

const MAX_DESTINATIONS: usize = 16;
const MAX_STORE_BYTES: usize = 128 * 1024;
const MAX_RECONCILIATIONS: usize = 64;
const APPROVAL_LIFETIME_MS: u64 = 60_000;
static NEXT_INSTANCE: AtomicU64 = AtomicU64::new(1);
static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct DestinationHost(String);

fn valid_ipv4(ip: Ipv4Addr) -> bool {
    !ip.is_unspecified() && !ip.is_multicast() && ip != Ipv4Addr::BROADCAST
}
impl TryFrom<String> for DestinationHost {
    type Error = anyhow::Error;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        anyhow::ensure!(
            !value.is_empty()
                && value.len() <= 253
                && value.is_ascii()
                && !value
                    .bytes()
                    .any(|b| b.is_ascii_whitespace() || b"/@?#%\\[]".contains(&b)),
            "INVALID_DESTINATION_HOST"
        );
        if let Ok(ip) = value.parse::<IpAddr>() {
            // OBS 33.0.1's librtmp passes URL brackets to mbedTLS's hostname
            // verifier. Do not advertise literal IPv6 until that path is fixed
            // and verified against an iPAddress SAN. DNS with AAAA stays valid.
            anyhow::ensure!(ip.is_ipv4(), "DESTINATION_IPV6_UNSUPPORTED");
            anyhow::ensure!(
                match ip {
                    IpAddr::V4(ip) => valid_ipv4(ip),
                    IpAddr::V6(_) => unreachable!(),
                },
                "INVALID_DESTINATION_HOST"
            );
            return Ok(Self(ip.to_string()));
        }
        anyhow::ensure!(!value.contains(':'), "INVALID_DESTINATION_HOST");
        let value = value.to_ascii_lowercase();
        if value == "localhost" {
            return Ok(Self(value));
        }
        let labels: Vec<_> = value.split('.').collect();
        anyhow::ensure!(labels.len() >= 2, "INVALID_DESTINATION_HOST");
        for label in &labels {
            anyhow::ensure!(
                !label.is_empty()
                    && label.len() <= 63
                    && label.as_bytes()[0].is_ascii_alphanumeric()
                    && label.as_bytes()[label.len() - 1].is_ascii_alphanumeric()
                    && label
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'-'),
                "INVALID_DESTINATION_HOST"
            );
        }
        // Reject legacy abbreviated/octal/hex address spellings that a resolver
        // might interpret as an IP despite not passing Rust's strict IP parser.
        let numeric_label = |label: &&str| {
            label.bytes().all(|b| b.is_ascii_digit())
                || label
                    .strip_prefix("0x")
                    .is_some_and(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_hexdigit()))
        };
        anyhow::ensure!(
            !labels.iter().all(numeric_label),
            "INVALID_DESTINATION_HOST"
        );
        anyhow::ensure!(
            labels
                .last()
                .unwrap()
                .bytes()
                .any(|b| b.is_ascii_alphabetic()),
            "INVALID_DESTINATION_HOST"
        );
        Ok(Self(value))
    }
}
impl From<DestinationHost> for String {
    fn from(value: DestinationHost) -> Self {
        value.0
    }
}
impl DestinationHost {
    pub fn as_str(&self) -> &str {
        &self.0
    }
    fn authority(&self) -> String {
        if self.0.contains(':') {
            format!("[{}]", self.0)
        } else {
            self.0.clone()
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct ApplicationPath(String);
impl TryFrom<String> for ApplicationPath {
    type Error = anyhow::Error;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        anyhow::ensure!(
            value.starts_with('/') && value.len() <= 256,
            "INVALID_DESTINATION_APPLICATION"
        );
        let segments: Vec<_> = value[1..].split('/').collect();
        anyhow::ensure!(
            !segments.is_empty() && segments.len() <= 8,
            "INVALID_DESTINATION_APPLICATION"
        );
        for segment in segments {
            anyhow::ensure!(
                !segment.is_empty()
                    && segment.len() <= 64
                    && segment != "."
                    && segment != ".."
                    && segment
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b)),
                "INVALID_DESTINATION_APPLICATION"
            );
        }
        Ok(Self(value))
    }
}
impl From<ApplicationPath> for String {
    fn from(value: ApplicationPath) -> Self {
        value.0
    }
}
impl ApplicationPath {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DestinationProtocol {
    Rtmps,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DestinationSpec {
    pub id: String,
    pub name: String,
    pub protocol: DestinationProtocol,
    pub host: DestinationHost,
    pub port: u16,
    pub application: ApplicationPath,
    pub credential_ref: Option<String>,
}
impl DestinationSpec {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            !self.id.is_empty()
                && self.id.len() <= 48
                && self
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"-_".contains(&b)),
            "INVALID_DESTINATION_ID"
        );
        anyhow::ensure!(
            !self.name.trim().is_empty()
                && self.name == self.name.trim()
                && self.name.chars().count() <= 80
                && !self.name.chars().any(char::is_control),
            "INVALID_DESTINATION_NAME"
        );
        anyhow::ensure!(self.port != 0, "INVALID_DESTINATION_PORT");
        anyhow::ensure!(
            self.credential_ref
                .as_ref()
                .is_none_or(|r| valid_credential_ref(r)),
            "INVALID_CREDENTIAL_REFERENCE"
        );
        Ok(())
    }
    /// Constructed from validated pieces; never accepts a client URL or key.
    pub fn server_url(&self) -> String {
        format!(
            "rtmps://{}:{}{}",
            self.host.authority(),
            self.port,
            self.application.as_str()
        )
    }
    /// Version 2 is deliberately incompatible with H8's port-only binding.
    /// The canonical bytes are native Keychain metadata, not the secret.
    pub fn credential_binding(&self) -> anyhow::Result<String> {
        self.validate()?;
        #[derive(Serialize)]
        struct Binding<'a> {
            version: u8,
            destination_id: &'a str,
            protocol: &'a str,
            host: &'a str,
            port: u16,
            application: &'a str,
        }
        Ok(serde_json::to_string(&Binding {
            version: 2,
            destination_id: &self.id,
            protocol: "rtmps",
            host: self.host.as_str(),
            port: self.port,
            application: self.application.as_str(),
        })?)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalState {
    Draft,
    Approved,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DestinationRecord {
    pub destination: DestinationSpec,
    pub approval: ApprovalState,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DestinationStore {
    pub version: u8,
    pub destinations: Vec<DestinationRecord>,
}
impl Default for DestinationStore {
    fn default() -> Self {
        Self {
            version: 1,
            destinations: Vec::new(),
        }
    }
}
impl DestinationStore {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.version == 1 && self.destinations.len() <= MAX_DESTINATIONS,
            "INVALID_DESTINATIONS"
        );
        let mut ids = BTreeSet::new();
        for record in &self.destinations {
            record.destination.validate()?;
            anyhow::ensure!(
                ids.insert(&record.destination.id),
                "DUPLICATE_DESTINATION_ID"
            );
        }
        Ok(())
    }
    pub fn from_json(bytes: &[u8]) -> anyhow::Result<Self> {
        anyhow::ensure!(
            bytes.len() <= MAX_STORE_BYTES,
            "DESTINATION_STORE_TOO_LARGE"
        );
        let store: Self =
            serde_json::from_slice(bytes).map_err(|_| anyhow::anyhow!("INVALID_DESTINATIONS"))?;
        store.validate()?;
        Ok(store)
    }
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        Self::from_json(&read_private_json(path)?)
    }
    pub fn save(&self, path: &Path) -> anyhow::Result<()> {
        self.validate()?;
        write_private_json(path, &serde_json::to_vec_pretty(self)?)
    }
}

/// Metadata only: the exact tuple shown by secure entry plus its opaque result.
/// Retained before association, including cancellation/stale completion, so a
/// normal shutdown cannot discard the sole reference to a saved Keychain item.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CredentialReceipt {
    pub request_id: u64,
    pub owner_pid: u32,
    pub requested_revision: u64,
    pub destination: DestinationSpec,
    pub binding: String,
    pub phase: StoredCredentialPhase,
    pub credential_ref: String,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum StoredCredentialPhase {
    Stored,
    StoredAfterCancel,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CredentialReceipts {
    pub version: u8,
    pub receipts: Vec<CredentialReceipt>,
}
impl Default for CredentialReceipts {
    fn default() -> Self {
        Self {
            version: 1,
            receipts: Vec::new(),
        }
    }
}
impl CredentialReceipts {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.version == 1 && self.receipts.len() <= MAX_RECONCILIATIONS,
            "INVALID_CREDENTIAL_RECEIPTS"
        );
        let mut ids = BTreeSet::new();
        for receipt in &self.receipts {
            receipt.destination.validate()?;
            anyhow::ensure!(
                receipt.request_id != 0
                    && receipt.owner_pid != 0
                    && ids.insert(receipt.request_id)
                    && receipt.destination.credential_ref.is_none()
                    && valid_credential_ref(&receipt.credential_ref)
                    && receipt.destination.credential_binding()? == receipt.binding,
                "INVALID_CREDENTIAL_RECEIPT"
            );
        }
        Ok(())
    }
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        let store: Self = serde_json::from_slice(&read_private_json(path)?)
            .map_err(|_| anyhow::anyhow!("INVALID_CREDENTIAL_RECEIPTS"))?;
        store.validate()?;
        Ok(store)
    }
    pub fn save(&self, path: &Path) -> anyhow::Result<()> {
        self.validate()?;
        write_private_json(path, &serde_json::to_vec_pretty(self)?)
    }
    pub fn has_capacity(&self) -> bool {
        self.receipts.len() < MAX_RECONCILIATIONS
    }
}

fn read_private_json(path: &Path) -> anyhow::Result<Vec<u8>> {
    private_parent(path)?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    let metadata = file.metadata()?;
    anyhow::ensure!(
        metadata.is_file()
            && metadata.uid() == unsafe { libc::geteuid() }
            && metadata.permissions().mode() & 0o777 == 0o600
            && metadata.len() <= MAX_STORE_BYTES as u64,
        "INVALID_DESTINATION_STORE_FILE"
    );
    let mut bytes = Vec::new();
    file.take((MAX_STORE_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    anyhow::ensure!(
        bytes.len() <= MAX_STORE_BYTES,
        "DESTINATION_STORE_TOO_LARGE"
    );
    Ok(bytes)
}
fn write_private_json(path: &Path, bytes: &[u8]) -> anyhow::Result<()> {
    let parent = private_parent(path)?;
    if let Ok(metadata) = path.symlink_metadata() {
        anyhow::ensure!(
            metadata.is_file()
                && metadata.uid() == unsafe { libc::geteuid() }
                && metadata.permissions().mode() & 0o777 == 0o600,
            "INVALID_DESTINATION_STORE_FILE"
        );
    }
    anyhow::ensure!(
        bytes.len() <= MAX_STORE_BYTES,
        "DESTINATION_STORE_TOO_LARGE"
    );
    let serial = NEXT_TEMP_FILE
        .try_update(Ordering::Relaxed, Ordering::Relaxed, |n| n.checked_add(1))
        .map_err(|_| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
    let temporary =
        path.with_file_name(format!(".destinations-{}-{serial}.tmp", std::process::id()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&temporary)?;
    let mut temporary_owned = true;
    let result = (|| -> anyhow::Result<()> {
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
        temporary_owned = false;
        parent.sync_all()?;
        Ok(())
    })();
    // Only our freshly-created temporary path, never the previous store.
    if result.is_err() && temporary_owned {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    const REF: &str = "kc_12345678-1234-1234-1234-123456789abc";
    fn spec() -> DestinationSpec {
        DestinationSpec {
            id: "private-test".into(),
            name: "Private test".into(),
            protocol: DestinationProtocol::Rtmps,
            host: "stream.example.com".to_owned().try_into().unwrap(),
            port: 443,
            application: "/live".to_owned().try_into().unwrap(),
            credential_ref: Some(REF.into()),
        }
    }
    fn registry() -> DestinationRegistry {
        let mut registry = DestinationRegistry::new(DestinationStore::default()).unwrap();
        registry.upsert_local(spec()).unwrap();
        let review = registry.review_local("private-test").unwrap();
        registry.approve_local(review).unwrap();
        registry.select_approved("private-test").unwrap();
        registry
            .preflight("private-test", CredentialCheck::Available)
            .unwrap();
        registry
    }
    fn owner() -> OwnerRevision {
        OwnerRevision {
            pid: 71,
            revision: 10,
        }
    }
    #[test]
    fn host_normalization_is_explicit_and_urls_are_never_accepted() {
        for (input, expected) in [
            ("STREAM.Example.COM", "stream.example.com"),
            ("192.0.2.1", "192.0.2.1"),
            ("LOCALHOST", "localhost"),
        ] {
            assert_eq!(
                DestinationHost::try_from(input.to_owned())
                    .unwrap()
                    .as_str(),
                expected
            );
        }
        for input in [
            "",
            "stream",
            "rtmps://example.com",
            "example.com:443",
            "user@example.com",
            "example.com/stream",
            "example.com?key=x",
            "example.com#key",
            "example.com.",
            ".example.com",
            "a..com",
            "-a.com",
            "a-.com",
            "a_b.com",
            "éxample.com",
            "example.com\n",
            " example.com",
            "example%2ecom",
            "[::1]",
            "::1",
            "2001:db8::1",
            "fe80::1%en0",
            "fe80::1",
            "::",
            "ff02::1",
            "0.0.0.0",
            "255.255.255.255",
            "224.0.0.1",
            "127.1",
            "127.000.0.1",
            "2130706433",
            "0x7f000001",
            "0x7f.0x0.0x0.0x1",
            "999.1.2.3",
            "stream.123",
        ] {
            assert!(
                DestinationHost::try_from(input.to_owned()).is_err(),
                "{input}"
            );
        }
        assert!(DestinationHost::try_from(format!("{}.com", "a".repeat(64))).is_err());
    }
    #[test]
    fn application_is_a_bounded_literal_path_without_key_query_or_escaping() {
        for value in ["/live", "/app/room_1-a.b"] {
            assert!(ApplicationPath::try_from(value.to_owned()).is_ok());
        }
        for value in [
            "",
            "/",
            "live",
            "//live",
            "/live/",
            "/./live",
            "/live/..",
            "/%2e%2e/live",
            "/live?key=secret",
            "/live#x",
            "/live\\room",
            "/live@room",
            "/live:room",
            "/live room",
            "/líve",
            "/live\n",
        ] {
            assert!(
                ApplicationPath::try_from(value.to_owned()).is_err(),
                "{value}"
            );
        }
        assert!(ApplicationPath::try_from(format!("/{}", "a".repeat(65))).is_err());
    }
    #[test]
    fn ipv6_literals_fail_explicitly_and_exact_version_two_binding_is_unambiguous() {
        for host in ["::1", "2001:db8::1", "::ffff:192.0.2.1"] {
            assert_eq!(
                DestinationHost::try_from(host.to_owned())
                    .unwrap_err()
                    .to_string(),
                "DESTINATION_IPV6_UNSUPPORTED"
            );
        }
        let mut spec = spec();
        spec.host = "192.0.2.1".to_owned().try_into().unwrap();
        assert_eq!(spec.server_url(), "rtmps://192.0.2.1:443/live");
        let binding: serde_json::Value =
            serde_json::from_str(&spec.credential_binding().unwrap()).unwrap();
        assert_eq!(binding["version"], 2);
        assert_eq!(binding["destination_id"], "private-test");
        assert_eq!(binding["host"], "192.0.2.1");
        assert!(binding.get("credential_ref").is_none());
        let original = spec.credential_binding().unwrap();
        spec.application = "/other".to_owned().try_into().unwrap();
        assert_ne!(original, spec.credential_binding().unwrap());
    }
    #[test]
    fn store_rejects_unknown_protocol_fields_versions_and_secret_refs() {
        let base = serde_json::to_value(DestinationStore {
            version: 1,
            destinations: vec![DestinationRecord {
                destination: spec(),
                approval: ApprovalState::Draft,
            }],
        })
        .unwrap();
        let reject = |value: serde_json::Value| {
            assert!(DestinationStore::from_json(&serde_json::to_vec(&value).unwrap()).is_err())
        };
        for (field, invalid) in [
            ("protocol", serde_json::json!("rtmp")),
            ("port", serde_json::json!(0)),
            ("port", serde_json::json!(65536)),
            ("port", serde_json::json!(-1)),
            ("credential_ref", serde_json::json!("plaintext-key")),
            (
                "credential_ref",
                serde_json::json!("kc_12345678-1234-1234-1234-123456789ABC"),
            ),
            ("stream_key", serde_json::json!("secret")),
            ("verify_tls", serde_json::json!(false)),
        ] {
            let mut value = base.clone();
            value["destinations"][0]["destination"][field] = invalid;
            reject(value);
        }
        let mut version = base.clone();
        version["version"] = 2.into();
        reject(version);
        let mut field = base.clone();
        field["selected"] = "private-test".into();
        reject(field);
        let mut duplicate = base.clone();
        duplicate["destinations"]
            .as_array_mut()
            .unwrap()
            .push(base["destinations"][0].clone());
        reject(duplicate);
    }
    #[test]
    fn local_review_never_survives_destination_edit() {
        let mut registry = DestinationRegistry::new(DestinationStore::default()).unwrap();
        registry.upsert_local(spec()).unwrap();
        assert!(registry.select_approved("private-test").is_err());
        let review = registry.review_local("private-test").unwrap();
        let mut updated = spec();
        updated.port = 8443;
        registry.upsert_local(updated).unwrap();
        assert!(registry.approve_local(review).is_err());
        assert_eq!(registry.list()[0].approval, ApprovalState::Draft);
    }
    #[test]
    fn stale_secure_entry_cannot_attach_credential_to_a_changed_destination() {
        let mut registry = registry();
        let binding = spec().credential_binding().unwrap();
        let mut changed = spec();
        changed.port = 8443;
        registry.upsert_local(changed).unwrap();
        assert!(
            registry
                .associate_credential_local("private-test", &binding, REF.into())
                .is_err()
        );
        let binding = registry.store.destinations[0]
            .destination
            .credential_binding()
            .unwrap();
        registry
            .associate_credential_local("private-test", &binding, REF.into())
            .unwrap();
        assert_eq!(registry.list()[0].approval, ApprovalState::Draft);
    }
    #[test]
    fn same_server_can_host_separately_approved_accounts_with_distinct_bindings() {
        let first = spec();
        let mut second = spec();
        second.id = "second-account".into();
        assert_ne!(
            first.credential_binding().unwrap(),
            second.credential_binding().unwrap()
        );
        DestinationStore {
            version: 1,
            destinations: vec![
                DestinationRecord {
                    destination: first,
                    approval: ApprovalState::Draft,
                },
                DestinationRecord {
                    destination: second,
                    approval: ApprovalState::Draft,
                },
            ],
        }
        .validate()
        .unwrap();
    }
    #[test]
    fn preflight_proves_configuration_only_and_ref_is_not_credential_access() {
        let mut registry = registry();
        for check in [
            CredentialCheck::Missing,
            CredentialCheck::AccessDenied,
            CredentialCheck::BindingMismatch,
            CredentialCheck::Unavailable,
        ] {
            assert!(registry.preflight("private-test", check).is_err());
        }
        let result = registry
            .preflight("private-test", CredentialCheck::Available)
            .unwrap();
        assert!(result.tls_required && result.ready && !result.network_tested);
        let mut missing = spec();
        missing.credential_ref = None;
        registry.upsert_local(missing).unwrap();
        let review = registry.review_local("private-test").unwrap();
        registry.approve_local(review).unwrap();
        assert!(
            registry
                .preflight("private-test", CredentialCheck::Available)
                .is_err()
        );
    }
    #[test]
    fn local_start_grants_bind_full_profile_revision_identity_and_lifetime() {
        let profile = OutputProfile::default();
        for change in [
            "pid",
            "revision",
            "profile",
            "expiry",
            "backward-clock",
            "registry",
        ] {
            let current = registry();
            let request = current
                .prepare_local_start(owner(), profile.clone(), 100)
                .unwrap();
            let mut current_owner = owner();
            let mut current_profile = profile.clone();
            let mut now = 101;
            match change {
                "pid" => current_owner.pid += 1,
                "revision" => current_owner.revision += 1,
                "profile" => current_profile.bitrate_kbps += 1,
                "expiry" => now = 60_100,
                "backward-clock" => now = 99,
                _ => {}
            }
            let result = if change == "registry" {
                registry().confirm_local_start(request, current_owner, &current_profile, now)
            } else {
                current.confirm_local_start(request, current_owner, &current_profile, now)
            };
            assert!(result.is_err(), "{change}");
        }
    }
    #[test]
    fn approved_start_is_one_use_and_invalidates_parallel_grants() {
        let mut registry = registry();
        let profile = OutputProfile::default();
        let first = registry
            .prepare_local_start(owner(), profile.clone(), 100)
            .unwrap();
        let second = registry
            .prepare_local_start(owner(), profile.clone(), 100)
            .unwrap();
        let first = registry
            .confirm_local_start(first, owner(), &profile, 101)
            .unwrap();
        let second = registry
            .confirm_local_start(second, owner(), &profile, 101)
            .unwrap();
        let (destination, effective) = registry
            .consume_local_start(first, owner(), &profile, 102, CredentialCheck::Available)
            .unwrap()
            .into_parts();
        assert_eq!(destination, spec());
        assert_eq!(effective, profile);
        assert!(
            registry
                .consume_local_start(second, owner(), &profile, 102, CredentialCheck::Available)
                .is_err()
        );
    }
    #[test]
    fn editing_removing_reselecting_or_reloading_invalidates_local_grant() {
        let profile = OutputProfile::default();
        for change in ["edit", "remove", "select", "load"] {
            let mut registry = registry();
            let request = registry
                .prepare_local_start(owner(), profile.clone(), 100)
                .unwrap();
            let grant = registry
                .confirm_local_start(request, owner(), &profile, 101)
                .unwrap();
            match change {
                "edit" => {
                    let mut next = spec();
                    next.name = "Changed name".into();
                    registry.upsert_local(next).unwrap();
                }
                "remove" => registry.remove_local("private-test").unwrap(),
                "select" => registry.select_approved("private-test").unwrap(),
                "load" => registry = DestinationRegistry::new(registry.store().clone()).unwrap(),
                _ => unreachable!(),
            }
            assert!(
                registry
                    .consume_local_start(grant, owner(), &profile, 102, CredentialCheck::Available)
                    .is_err(),
                "{change}"
            );
        }
    }
    #[test]
    fn persistence_is_private_atomic_and_never_restores_selection_or_validation() {
        let dir = std::env::temp_dir().join(format!(
            "motive-destinations-{}-{}",
            std::process::id(),
            NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        let path = dir.join("destinations.json");
        let registry = registry();
        registry.store().save(&path).unwrap();
        let restored = DestinationRegistry::new(DestinationStore::load(&path).unwrap()).unwrap();
        assert!(restored.selected().is_none());
        assert_eq!(restored.list()[0].validation, ValidationState::Unchecked);
        let bytes = fs::read(&path).unwrap();
        assert!(!String::from_utf8_lossy(&bytes).contains("selected"));
        let link = dir.join("linked.json");
        symlink(&path, &link).unwrap();
        assert!(DestinationStore::load(&link).is_err());
        assert!(registry.store().save(&link).is_err());
        assert_eq!(bytes, fs::read(&path).unwrap());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(DestinationStore::load(&path).is_err());
        assert!(registry.store().save(&path).is_err());
        fs::remove_dir_all(dir).unwrap();
    }
}
fn private_parent(path: &Path) -> anyhow::Result<File> {
    anyhow::ensure!(
        path.is_absolute() && path.file_name().is_some(),
        "INVALID_DESTINATION_STORE_PATH"
    );
    let parent = path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("INVALID_DESTINATION_STORE_PATH"))?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC)
        .open(parent)?;
    let metadata = file.metadata()?;
    anyhow::ensure!(
        metadata.is_dir()
            && metadata.uid() == unsafe { libc::geteuid() }
            && metadata.permissions().mode() & 0o777 == 0o700,
        "DESTINATION_DIRECTORY_NOT_PRIVATE"
    );
    Ok(file)
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ValidationState {
    Unchecked,
    ConfigurationReady,
    CredentialMissing,
    CredentialAccessDenied,
    CredentialBindingMismatch,
    KeychainUnavailable,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CredentialCheck {
    Available,
    Missing,
    AccessDenied,
    BindingMismatch,
    Unavailable,
}
impl CredentialCheck {
    fn validate(self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self == Self::Available,
            "{}",
            match self {
                Self::Available => "available",
                Self::Missing => "CREDENTIAL_MISSING",
                Self::AccessDenied => "CREDENTIAL_ACCESS_DENIED",
                Self::BindingMismatch => "CREDENTIAL_BINDING_MISMATCH",
                Self::Unavailable => "KEYCHAIN_UNAVAILABLE",
            }
        );
        Ok(())
    }
    fn state(self) -> ValidationState {
        match self {
            Self::Available => ValidationState::ConfigurationReady,
            Self::Missing => ValidationState::CredentialMissing,
            Self::AccessDenied => ValidationState::CredentialAccessDenied,
            Self::BindingMismatch => ValidationState::CredentialBindingMismatch,
            Self::Unavailable => ValidationState::KeychainUnavailable,
        }
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct DestinationView {
    pub destination: DestinationSpec,
    pub approval: ApprovalState,
    pub validation: ValidationState,
    pub selected: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct DestinationPreflight {
    pub destination_id: String,
    pub tls_required: bool,
    pub network_tested: bool,
    pub ready: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct OwnerRevision {
    pub pid: u32,
    pub revision: u64,
}

/// Only the owner method called by local UI can construct this review request.
pub struct LocalDestinationReview {
    instance: u64,
    generation: u64,
    destination: DestinationSpec,
}
impl LocalDestinationReview {
    pub fn destination(&self) -> &DestinationSpec {
        &self.destination
    }
}

/// Deliberately not Clone, Serialize or Deserialize. A dialog is not approval.
pub struct LocalStartRequest {
    instance: u64,
    generation: u64,
    owner: OwnerRevision,
    destination: DestinationSpec,
    profile: OutputProfile,
    issued_ms: u64,
    expires_ms: u64,
}
impl LocalStartRequest {
    pub fn destination(&self) -> &DestinationSpec {
        &self.destination
    }
    pub fn profile(&self) -> &OutputProfile {
        &self.profile
    }
}
/// Only affirmative local UI consumes a request into this one-use capability.
pub struct LocalStartGrant(LocalStartRequest);
pub struct AuthorizedDestinationStart {
    destination: DestinationSpec,
    profile: OutputProfile,
}
impl AuthorizedDestinationStart {
    pub fn into_parts(self) -> (DestinationSpec, OutputProfile) {
        (self.destination, self.profile)
    }
}

pub struct DestinationRegistry {
    store: DestinationStore,
    selected: Option<String>,
    validation: BTreeMap<String, ValidationState>,
    instance: u64,
    generation: u64,
}
impl DestinationRegistry {
    /// Private transaction copy; never expose Clone on the authority registry.
    pub(super) fn staged(&self) -> Self {
        Self {
            store: self.store.clone(),
            selected: self.selected.clone(),
            validation: self.validation.clone(),
            instance: self.instance,
            generation: self.generation,
        }
    }
    /// A failed save can occur after rename. Freeze this owner instead of
    /// pretending the disk rolled back or keeping a prepared start usable.
    pub(super) fn suspend(&mut self) {
        self.selected = None;
        self.validation.clear();
    }
    pub(super) fn receipt_attached(&self, receipt: &CredentialReceipt) -> bool {
        self.store.destinations.iter().any(|record| {
            record.destination.credential_ref.as_deref() == Some(&receipt.credential_ref)
                && record.destination.credential_binding().ok().as_deref() == Some(&receipt.binding)
        })
    }
    pub fn new(store: DestinationStore) -> anyhow::Result<Self> {
        store.validate()?;
        let instance = NEXT_INSTANCE
            .try_update(Ordering::Relaxed, Ordering::Relaxed, |n| n.checked_add(1))
            .map_err(|_| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        Ok(Self {
            store,
            selected: None,
            validation: BTreeMap::new(),
            instance,
            generation: 0,
        })
    }
    pub fn store(&self) -> &DestinationStore {
        &self.store
    }
    pub fn list(&self) -> Vec<DestinationView> {
        self.store
            .destinations
            .iter()
            .map(|record| DestinationView {
                destination: record.destination.clone(),
                approval: record.approval,
                validation: self
                    .validation
                    .get(&record.destination.id)
                    .copied()
                    .unwrap_or(ValidationState::Unchecked),
                selected: self.selected.as_deref() == Some(&record.destination.id),
            })
            .collect()
    }
    pub fn selected(&self) -> Option<&str> {
        self.selected.as_deref()
    }
    pub fn clear_selection(&mut self) -> anyhow::Result<()> {
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        self.selected = None;
        Ok(())
    }
    pub fn approved(&self, id: &str) -> anyhow::Result<&DestinationSpec> {
        let record = self
            .store
            .destinations
            .iter()
            .find(|r| r.destination.id == id)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_UNAVAILABLE"))?;
        anyhow::ensure!(
            record.approval == ApprovalState::Approved,
            "DESTINATION_NOT_APPROVED"
        );
        Ok(&record.destination)
    }
    /// Safe public operation: IDs already admitted to the private registry only.
    pub fn select_approved(&mut self, id: &str) -> anyhow::Result<()> {
        self.approved(id)?;
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        self.selected = Some(id.into());
        Ok(())
    }
    pub fn preflight(
        &mut self,
        id: &str,
        credential: CredentialCheck,
    ) -> anyhow::Result<DestinationPreflight> {
        let spec = self.approved(id)?;
        let credential = if spec.credential_ref.is_none() {
            CredentialCheck::Missing
        } else {
            credential
        };
        self.validation.insert(id.into(), credential.state());
        credential.validate()?;
        Ok(DestinationPreflight {
            destination_id: id.into(),
            tls_required: true,
            network_tested: false,
            ready: true,
        })
    }
    /// Owner-only local UI path. Never add this operation to Command/MCP.
    pub(super) fn upsert_local(&mut self, destination: DestinationSpec) -> anyhow::Result<()> {
        destination.validate()?;
        let mut candidate = self.store.clone();
        let record = DestinationRecord {
            destination: destination.clone(),
            approval: ApprovalState::Draft,
        };
        if let Some(old) = candidate
            .destinations
            .iter_mut()
            .find(|r| r.destination.id == destination.id)
        {
            *old = record;
        } else {
            candidate.destinations.push(record);
        }
        candidate.validate()?;
        let generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        self.store = candidate;
        self.generation = generation;
        self.validation.remove(&destination.id);
        if self.selected.as_deref() == Some(&destination.id) {
            self.selected = None;
        }
        Ok(())
    }
    /// Associate only the exact destination tuple shown by native secure entry.
    /// A stale completion may remain in Keychain, but cannot bind to an edited host.
    pub(super) fn associate_credential_local(
        &mut self,
        id: &str,
        expected_binding: &str,
        credential_ref: String,
    ) -> anyhow::Result<()> {
        let mut destination = self
            .store
            .destinations
            .iter()
            .find(|r| r.destination.id == id)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_UNAVAILABLE"))?
            .destination
            .clone();
        anyhow::ensure!(
            destination.credential_binding()? == expected_binding,
            "STALE_CREDENTIAL_ENROLLMENT"
        );
        anyhow::ensure!(
            valid_credential_ref(&credential_ref),
            "INVALID_CREDENTIAL_REFERENCE"
        );
        destination.credential_ref = Some(credential_ref);
        self.upsert_local(destination)
    }
    pub(super) fn review_local(&self, id: &str) -> anyhow::Result<LocalDestinationReview> {
        let record = self
            .store
            .destinations
            .iter()
            .find(|r| r.destination.id == id)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_UNAVAILABLE"))?;
        Ok(LocalDestinationReview {
            instance: self.instance,
            generation: self.generation,
            destination: record.destination.clone(),
        })
    }
    pub(super) fn approve_local(&mut self, review: LocalDestinationReview) -> anyhow::Result<()> {
        anyhow::ensure!(
            review.instance == self.instance && review.generation == self.generation,
            "STALE_DESTINATION_REVIEW"
        );
        let record = self
            .store
            .destinations
            .iter_mut()
            .find(|r| r.destination == review.destination)
            .ok_or_else(|| anyhow::anyhow!("STALE_DESTINATION_REVIEW"))?;
        let generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        record.approval = ApprovalState::Approved;
        self.generation = generation;
        Ok(())
    }
    pub(super) fn remove_local(&mut self, id: &str) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.store
                .destinations
                .iter()
                .any(|r| r.destination.id == id),
            "DESTINATION_UNAVAILABLE"
        );
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        self.store.destinations.retain(|r| r.destination.id != id);
        self.validation.remove(id);
        if self.selected.as_deref() == Some(id) {
            self.selected = None;
        }
        Ok(())
    }
    pub(super) fn prepare_local_start(
        &self,
        owner: OwnerRevision,
        profile: OutputProfile,
        now_ms: u64,
    ) -> anyhow::Result<LocalStartRequest> {
        anyhow::ensure!(owner.pid != 0, "INVALID_OWNER");
        profile.validate()?;
        let id = self
            .selected
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_NOT_SELECTED"))?;
        let destination = self.approved(id)?.clone();
        anyhow::ensure!(
            self.validation.get(id) == Some(&ValidationState::ConfigurationReady),
            "DESTINATION_PREFLIGHT_REQUIRED"
        );
        Ok(LocalStartRequest {
            instance: self.instance,
            generation: self.generation,
            owner,
            destination,
            profile,
            issued_ms: now_ms,
            expires_ms: now_ms
                .checked_add(APPROVAL_LIFETIME_MS)
                .ok_or_else(|| anyhow::anyhow!("CLOCK_EXHAUSTED"))?,
        })
    }
    fn check_request(
        &self,
        request: &LocalStartRequest,
        owner: OwnerRevision,
        profile: &OutputProfile,
        now_ms: u64,
    ) -> anyhow::Result<()> {
        anyhow::ensure!(
            request.instance == self.instance
                && request.generation == self.generation
                && request.owner == owner
                && &request.profile == profile
                && self.selected.as_deref() == Some(&request.destination.id)
                && self.approved(&request.destination.id)? == &request.destination,
            "STALE_STREAM_APPROVAL"
        );
        anyhow::ensure!(
            now_ms >= request.issued_ms && now_ms < request.expires_ms,
            "STREAM_APPROVAL_EXPIRED"
        );
        Ok(())
    }
    pub(super) fn confirm_local_start(
        &self,
        request: LocalStartRequest,
        owner: OwnerRevision,
        profile: &OutputProfile,
        now_ms: u64,
    ) -> anyhow::Result<LocalStartGrant> {
        self.check_request(&request, owner, profile, now_ms)?;
        Ok(LocalStartGrant(request))
    }
    /// Consume before touching the native slot; every failure also spends it.
    pub(super) fn consume_local_start(
        &mut self,
        grant: LocalStartGrant,
        owner: OwnerRevision,
        profile: &OutputProfile,
        now_ms: u64,
        credential: CredentialCheck,
    ) -> anyhow::Result<AuthorizedDestinationStart> {
        self.check_request(&grant.0, owner, profile, now_ms)?;
        credential.validate()?;
        // Invalidates any other dialog/grant prepared before this start attempt.
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_ID_EXHAUSTED"))?;
        Ok(AuthorizedDestinationStart {
            destination: grant.0.destination,
            profile: grant.0.profile,
        })
    }
}
