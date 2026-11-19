"""Classifier regression, not native sandbox evidence."""
import copy
import errno
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from h19_security_check import classify, read_json


class NativeEvidenceClassification(unittest.TestCase):
    def setUp(self):
        self.native = {"native_executed": True, "scenario": "security", "instances": [{"instance": 1, "generation": 7, "browser_id": 1,
                                      "renderer_pid_reported": 123, "renderer_decoy_observed": True,
                                      "renderer_decoy_opened": False, "renderer_decoy_errno": errno.EPERM,
                                      "browser_decoy_opened": True, "browser_decoy_errno": 0,
                                      "closed": True, "failed": False}]}
        self.supervision = {"reason": "exit", "returncode": 0, "final_cleanup_observed_tree": True,
                            "final_remaining_observed_pids": [], "final_remaining_observed_live_pids": []}

    def result(self):
        return classify(self.native, self.supervision, 1, 7)

    def test_narrow_denial_never_authorizes_third_parties(self):
        result = self.result()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["third_party_execution"], "BLOCKED")
        self.assertEqual(result["complete_os_sandbox_matrix"], "BLOCKED")
        self.assertEqual(result["browser_process_filesystem_confinement"], "BLOCKED")

    def test_missing_file_is_not_denial(self):
        self.native["instances"][0]["renderer_decoy_errno"] = errno.ENOENT
        self.assertEqual(self.result()["status"], "FAIL")

    def test_browser_positive_control_is_required(self):
        self.native["instances"][0]["browser_decoy_opened"] = False
        self.assertEqual(self.result()["status"], "FAIL")

    def test_missing_probe_or_cleanup_cannot_pass(self):
        self.native["instances"][0]["renderer_decoy_observed"] = False
        self.assertEqual(self.result()["status"], "FAIL")
        self.native["instances"][0]["renderer_decoy_observed"] = True
        del self.supervision["final_remaining_observed_pids"]
        self.assertEqual(self.result()["status"], "FAIL")

    def test_foreign_generation_and_duplicate_identity_rejected(self):
        self.native["instances"][0]["generation"] = 6
        self.assertEqual(self.result()["status"], "FAIL")
        self.native["instances"][0]["generation"] = 7
        self.native["instances"].append(copy.deepcopy(self.native["instances"][0]))
        self.assertEqual(self.result()["status"], "FAIL")

    def test_renderer_allow_or_negative_pid_rejected(self):
        self.native["instances"][0]["renderer_decoy_opened"] = True
        self.assertEqual(self.result()["status"], "FAIL")
        self.native["instances"][0]["renderer_decoy_opened"] = False
        self.native["instances"][0]["renderer_pid_reported"] = -1
        self.assertEqual(self.result()["status"], "FAIL")

    def test_zero_listener_connections_is_not_os_network_proof(self):
        result = classify(self.native, self.supervision, 1, 7,
                          {"bound": True, "closed": True, "accepted_connections": 0})
        self.assertEqual(result["owned_loopback_canary"]["observation"], "NO_ACCEPTED_CONNECTIONS")
        self.assertEqual(result["network_os_confinement"], "NOT_EVALUATED")

    def test_compressed_and_nested_supervision_preserves_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "supervision.json.gz"
            path.write_bytes(gzip.compress(json.dumps(self.supervision).encode()))
            result = classify(self.native, read_json(path), 1, 7)
            self.assertEqual(result, self.result())
            self.assertEqual(classify(self.native, {"supervision": self.supervision}, 1, 7), result)

    def test_reported_pid_must_match_available_owned_process_evidence(self):
        self.supervision["samples"] = [{"resource_usage": {"processes": [
            {"pid": 123, "birth": [100, 200], "role": "renderer"}]}}]
        self.assertEqual(self.result()["probes"][0]["renderer_identity_corroboration"], "PASS")
        self.supervision["samples"][0]["resource_usage"]["processes"][0]["pid"] = 124
        self.assertEqual(self.result()["status"], "FAIL")

    def test_unexpected_web_probe_allow_does_not_pass(self):
        self.native["instances"][0]["security_phases"] = [21, 22, 24, 26, 28]
        self.assertEqual(self.result()["status"], "FAIL")
        self.native["instances"][0]["security_phases"] = [20, 22, 24, 26, 28]
        result = self.result()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(value == "OBSERVED_REJECTION" for value in result["probes"][0]["application_surface_observations"].values()))


if __name__ == "__main__":
    unittest.main()
