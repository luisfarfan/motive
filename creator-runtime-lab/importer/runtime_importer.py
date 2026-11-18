"""H18 offline review and private staging of the existing experimental container.

No Production connection, trust approval, archive extraction helper or script execution.
The caller supplies capabilities/policy; package metadata cannot grant either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from io import BytesIO
import os
from pathlib import Path
import secrets
import stat
import sys
from types import MappingProxyType
import zipfile

SDK = Path(__file__).resolve().parents[2] / "element-lab" / "sdk"
sys.path.insert(0, str(SDK))
from common import LabError, encode, loads, relative, require  # noqa: E402
from compiler import Bundle  # noqa: E402
from contracts import estimate  # noqa: E402
from packaging import BASELINE, MAX_TOTAL, verify_bytes  # noqa: E402

# The shipped GPL text, not an assertion that a third party owns its contributions.
GPL_TEXT_SHA256 = "fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0"
_ISSUER = object()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ReviewPolicy:
    """Local review inputs; never decoded from a package or used as owner approval."""

    available_capabilities: frozenset[str] = frozenset()
    allowed_licenses: frozenset[str] = frozenset({"GPL-3.0-or-later"})
    approved_license_texts: frozenset[tuple[str, str]] = frozenset({("GPL-3.0-or-later", GPL_TEXT_SHA256)})
    supported_baselines: frozenset[str] = frozenset({BASELINE})
    max_resource_bytes: int = MAX_TOTAL
    max_staging_bytes: int = 2 * MAX_TOTAL + 1_048_576

    def __post_init__(self):
        require(type(self.max_resource_bytes) is int and 0 <= self.max_resource_bytes <= MAX_TOTAL,
                "REVIEW_POLICY", "Resource ceiling must remain within the experimental container limit")
        require(type(self.max_staging_bytes) is int and 0 <= self.max_staging_bytes <= 2 * MAX_TOTAL + 1_048_576,
                "REVIEW_POLICY", "Staging ceiling must remain within two bounded copies plus metadata")
        for name in ("available_capabilities", "allowed_licenses", "approved_license_texts", "supported_baselines"):
            object.__setattr__(self, name, frozenset(getattr(self, name)))


@dataclass(frozen=True)
class ReviewedPackage:
    """Immutable byte snapshot. JSON accessors return independent mutable copies."""

    _archive: bytes = field(repr=False)
    _files: tuple[tuple[str, bytes], ...] = field(repr=False)
    _report_json: bytes = field(repr=False)
    _issuer: object = field(repr=False)

    @property
    def sha256(self):
        return _sha(self._archive)

    @property
    def package_id(self):
        return self.metadata["id"]

    @property
    def version(self):
        return self.metadata["version"]

    @property
    def metadata(self):
        return loads(dict(self._files)["package.json"])

    @property
    def manifest(self):
        return loads(dict(self._files)["manifest.json"])

    @property
    def rules(self):
        return loads(dict(self._files)["rules.json"])

    @property
    def assets(self):
        return MappingProxyType({name.removeprefix("assets/"): data for name, data in self._files
                                 if name.startswith("assets/")})

    @property
    def inventory(self):
        return tuple(MappingProxyType({"path": name, "bytes": len(data), "sha256": _sha(data)})
                     for name, data in self._files)

    @property
    def report(self):
        return loads(self._report_json)

    def as_bundle(self):
        """Existing SDK type; mutating it cannot alter this reviewed snapshot."""
        return Bundle(self.manifest, self.rules, dict(self.assets), self.report["contract"])


def _open_directory(path: Path) -> int:
    """Walk every absolute component with no-follow, not merely the final parent."""
    absolute = Path(os.path.abspath(path))
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except OSError as exc:
        os.close(fd)
        raise LabError("FILE_BOUNDARY", "Selected directory must contain no symlink components") from exc


def _read_at(directory: int, name: str, limit: int) -> bytes:
    """Read one regular inode; all parent components already have held descriptors."""
    require("/" not in relative(name), "PATH", "A basename is required at this boundary")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                    0 < before.st_size <= limit, "FILE_BOUNDARY", "Bounded regular file with one link required")
            chunks, count = [], 0
            while True:
                chunk = os.read(fd, min(65536, limit + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                require(count <= limit, "FILE_SIZE", "Selected file exceeds the bound")
                chunks.append(chunk)
            after = os.fstat(fd)
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns) and count == after.st_size,
                    "FILE_CHANGED", "Selected file changed during review")
            return b"".join(chunks)
        finally:
            os.close(fd)
    except OSError as exc:
        raise LabError("FILE_BOUNDARY", "Cannot read a selected regular file without following links") from exc


def review_package(path: Path, policy: ReviewPolicy) -> ReviewedPackage:
    """Validate selected bytes once, using the existing SDK and actual Rust contract.

    The result is suitable for a proposal, never proof of native decoder acceptance,
    author identity, a local confirmation, or an official installation format.
    """
    require(isinstance(policy, ReviewPolicy), "REVIEW_POLICY", "Local ReviewPolicy required")
    path = Path(path)
    require(path.suffix == ".motivepack", "PACKAGE_EXTENSION", "Declarative .motivepack required; web execution is separate")
    directory = _open_directory(path.parent)
    try:
        data = _read_at(directory, path.name, MAX_TOTAL)
    finally:
        os.close(directory)
    # ZIP libraries truncate NUL filenames; reject ambiguous raw names before semantic review.
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            require(all(info.orig_filename == info.filename for info in archive.infolist()),
                    "PACKAGE_PATH", "ZIP entry names must not be NUL-truncated")
    except zipfile.BadZipFile as exc:
        raise LabError("PACKAGE_ZIP", "Malformed ZIP container") from exc
    verified = verify_bytes(data)
    require(verified["content_kind"] == "declarative_pack", "PACKAGE_KIND", "Web packages cannot enter the declarative importer")
    # Reopen only this immutable in-memory archive, never the user-selected path.
    with zipfile.ZipFile(BytesIO(data)) as archive:
        files = {info.filename: archive.read(info) for info in archive.infolist()}
    metadata, manifest = loads(files["package.json"]), loads(files["manifest.json"])
    require(metadata["compatibility"]["baseline"] in policy.supported_baselines,
            "PACKAGE_BASELINE", "The local policy has not reviewed this compatibility baseline")
    require(manifest["license"] in policy.allowed_licenses, "LICENSE_POLICY", "License is not admitted by the local review policy")
    license_hash = _sha(files["LICENSE"])
    require((manifest["license"], license_hash) in policy.approved_license_texts,
            "LICENSE_TEXT", "License text must match a separately reviewed local digest")
    missing = sorted(set(manifest["requires"]) - policy.available_capabilities)
    require(not missing, "CAPABILITY_UNAVAILABLE", "Missing locally supplied capabilities: " + ", ".join(missing))
    resource_bytes = sum(resource["bytes"] for resource in manifest["resources"])
    require(resource_bytes <= policy.max_resource_bytes, "RESOURCE_BUDGET", "Resources exceed the local review budget")
    used = {source["definition"]["resource_id"] for source in manifest["overlays"]
            if "resource_id" in source["definition"]}
    require(used == {resource["id"] for resource in manifest["resources"]},
            "RESOURCE_ORPHAN", "Every packaged resource must belong to the dependency closure")
    budget = estimate(manifest)
    inventory = [{"path": name, "bytes": len(content), "sha256": _sha(content)}
                 for name, content in sorted(files.items())]
    record = _stage_record("stage-" + "0" * 32, manifest["id"], manifest["version"], _sha(data), inventory)
    staging_bytes = len(data) + sum(map(len, files.values())) + len(record)
    require(staging_bytes <= policy.max_staging_bytes, "STAGING_BUDGET", "Private staging exceeds the local disk budget")
    report = {**verified, "package_version": metadata["package_version"], "version": manifest["version"],
              "container": metadata["format"], "official_installation_format": False,
              "package_sha256": _sha(data), "reviewed_for": "offline_installation_proposal",
              "owner_authorized": False, "rules_arming_authorized": False,
              "required_capabilities": manifest["requires"], "available_capabilities": sorted(policy.available_capabilities),
              "resource_bytes": resource_bytes, "budget": budget,
              "staging_bytes": staging_bytes, "staging_budget_bytes": policy.max_staging_bytes,
              "license": {"declared": manifest["license"], "text_sha256": license_hash,
                          "matches_local_policy": True, "ownership_verified": False,
                          "resource_attribution": "CreatorPack v1 inherits the pack license; per-resource provenance is not carried"},
              "dependencies": {"resources": sorted(used), "resolution": "embedded_inventory_only", "downloads": False},
              "native_asset_decoder_verified": False, "cleanup": "only owned staging objects, otherwise reconciliation required"}
    return ReviewedPackage(data, tuple(sorted(files.items())), encode(report), _ISSUER)


def _stage_record(operation_id, package_id, version, package_hash, inventory):
    return encode({"version": 1, "operation_id": operation_id, "package_id": package_id,
                   "package_version": version, "package_sha256": package_hash,
                   "format": "motive-element-lab-review", "owner_authorized": False,
                   "installed": False, "files": inventory})


def _identity(fd: int):
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def _write_at(fd: int, name: str, data: bytes):
    leaf = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=fd)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(leaf, remaining)
            require(written > 0, "STAGING_WRITE", "Short staging write")
            remaining = remaining[written:]
        os.fsync(leaf)
        return _identity(leaf)
    finally:
        os.close(leaf)


class StagedPackage:
    """Held directory descriptors and owned inode inventory, not a reusable trust token.

    Cleanup checks the complete tree before deleting anything. Foreign entries or
    replaced inodes fail closed with STAGING_RECONCILIATION; no recursive rmtree.
    Same-user hostile native code is not a sandbox this API claims to provide.
    """

    def __init__(self, reviewed: ReviewedPackage, root: Path):
        require(isinstance(reviewed, ReviewedPackage) and reviewed._issuer is _ISSUER,
                "REVIEW_REQUIRED", "Use review_package before staging")
        self.reviewed = reviewed
        self.root = Path(os.path.abspath(root))
        self.operation_id = "stage-" + secrets.token_hex(16)
        self.path = self.root / self.operation_id
        self._dirs: dict[str, int] = {}
        self._identities = {}
        self._files = {**dict(reviewed._files), "reviewed.motivepack": reviewed._archive}
        # No serialized trust flag; the record explains what was reviewed and staged.
        self._files["staging-record.json"] = _stage_record(self.operation_id, reviewed.package_id,
            reviewed.version, reviewed.sha256, [dict(item) for item in reviewed.inventory])
        self._closed = False
        self._cleaned = False
        parent = _open_directory(self.root.parent)
        try:
            try:
                os.mkdir(self.root.name, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
            self._root_fd = os.open(self.root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except OSError as exc:
            raise LabError("STAGING_ROOT", "Private staging root cannot be opened without following links") from exc
        finally:
            os.close(parent)
        try:
            info = os.fstat(self._root_fd)
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                    "STAGING_ROOT", "Staging root must be owned by this user with mode 0700 or stricter")
            os.mkdir(self.operation_id, 0o700, dir_fd=self._root_fd)
            self._dirs[""] = os.open(self.operation_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._root_fd)
            self._identities[""] = _identity(self._dirs[""])
            for name, data in sorted(self._files.items()):
                parts = relative(name).split("/")
                current = ""
                for part in parts[:-1]:
                    child = current + ("/" if current else "") + part
                    if child not in self._dirs:
                        os.mkdir(part, 0o700, dir_fd=self._dirs[current])
                        self._dirs[child] = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._dirs[current])
                        self._identities[child] = _identity(self._dirs[child])
                    current = child
                self._identities[name] = _write_at(self._dirs[current], parts[-1], data)
            for fd in self._dirs.values():
                os.fsync(fd)
            self.reverify()
        except Exception:
            # Interrupted writes may need explicit reconciliation. Never sweep foreign files.
            self.close()
            raise

    def _tree_unchanged(self):
        require(not self._closed, "STAGING_CLOSED", "Staging descriptors are closed")
        root_info = os.stat(self.operation_id, dir_fd=self._root_fd, follow_symlinks=False)
        require((root_info.st_dev, root_info.st_ino) == self._identities[""] and stat.S_ISDIR(root_info.st_mode),
                "STAGING_RECONCILIATION", "Operation directory identity changed")
        all_names = set(self._files) | (set(self._dirs) - {""})
        for directory, fd in self._dirs.items():
            prefix = directory + "/" if directory else ""
            expected = {name[len(prefix):] for name in all_names
                        if name.startswith(prefix) and "/" not in name[len(prefix):]}
            require(set(os.listdir(fd)) == expected, "STAGING_RECONCILIATION", "Staging contains missing or foreign entries")
            for name in expected:
                full = prefix + name
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                is_directory = full in self._dirs
                require((info.st_dev, info.st_ino) == self._identities[full] and
                        (stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
                        "STAGING_RECONCILIATION", "Owned staging inode was replaced or linked")

    def reverify(self) -> dict:
        try:
            self._tree_unchanged()
            for name, expected in self._files.items():
                parent, _, leaf = name.rpartition("/")
                actual = _read_at(self._dirs[parent], leaf, len(expected))
                require(actual == expected, "STAGING_HASH", "Staged bytes changed after review")
        except OSError as exc:
            raise LabError("STAGING_RECONCILIATION", "Staging tree no longer matches owned inventory") from exc
        return {"status": "PASS", "operation_id": self.operation_id,
                "package_sha256": self.reviewed.sha256, "files": len(self._files),
                "owner_authorized": False, "installed": False}

    def cleanup(self):
        if self._cleaned:
            return
        try:
            self._tree_unchanged()
            # No wildcard or recursive removal: only the inventoried owned objects.
            for name in self._files:
                parent, _, leaf = name.rpartition("/")
                os.unlink(leaf, dir_fd=self._dirs[parent])
            for name in sorted(set(self._dirs) - {""}, key=lambda s: s.count("/"), reverse=True):
                parent, _, leaf = name.rpartition("/")
                os.rmdir(leaf, dir_fd=self._dirs[parent])
            os.rmdir(self.operation_id, dir_fd=self._root_fd)
            self._cleaned = True
        except OSError as exc:
            raise LabError("STAGING_RECONCILIATION", "Cleanup interrupted; preserve remaining staging for review") from exc
        finally:
            self.close()

    def close(self):
        """Release handles without guessing recovery of interrupted/foreign state."""
        if not self._closed:
            for fd in self._dirs.values():
                os.close(fd)
            os.close(self._root_fd)
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()


def stage_package(reviewed: ReviewedPackage, staging_root: Path) -> StagedPackage:
    return StagedPackage(reviewed, staging_root)
