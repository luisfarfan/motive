"""Review/stage every shipped declarative example without touching Production."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile

from runtime_importer import ReviewPolicy, review_package, stage_package
from common import encode
from schemas import CAPABILITIES

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "creator-runtime-lab"


def main():
    # Explicit offline test policy, not capabilities observed from an active Motive.
    policy = ReviewPolicy(available_capabilities=frozenset(CAPABILITIES))
    scratch = LAB / ".scratch"
    scratch.mkdir(exist_ok=True)
    examples = []
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        for path in sorted((ROOT / "element-lab/marketplace-contract/packages").glob("*.motivepack")):
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            review = review_package(path, policy)
            with stage_package(review, Path(temporary) / "stages") as stage:
                staged = stage.reverify()
                stage_path = stage.path
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            assert before == after == review.sha256
            assert not stage_path.exists()
            examples.append({"package": path.name, "status": "PASS", "original_sha256": before,
                "original_unchanged": True, "package_id": review.package_id, "version": review.version,
                "budget": review.report["budget"], "staging_bytes": review.report["staging_bytes"],
                "staged_files": staged["files"], "staging_cleaned": True,
                "native_decode_verified": False, "owner_authorized": False, "installed": False})
    report = {"checkpoint": "H18 importer and staging", "created_utc": datetime.now(timezone.utc).isoformat(),
              "status": "PASS", "scope": "Seven real archives, offline Show Control contract, filesystem staging/cleanup",
              "production_connected": False, "official_format_ratified": False, "examples": examples}
    evidence = LAB / "evidence/H18-importer-examples.json"
    evidence.write_bytes(encode(report))
    print(encode(report).decode(), end="")


if __name__ == "__main__":
    main()
