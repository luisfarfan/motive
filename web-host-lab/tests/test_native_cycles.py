"""Aggregation/stop tests only: no CEF, browser, subprocess, or native evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

LAB = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_cycles_under_test", LAB / "tools/run_native_cycles.py")
cycles = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cycles
spec.loader.exec_module(cycles)


def fixture_report():
    supervision = {"reason": "exit", "returncode": 0, "final_cleanup_observed_tree": True,
                   "final_remaining_observed_pids": []}
    samples = {"first": {"counter": {"status": "NOT_EVALUATED", "value_modulo_256": None}},
               "latest": {"status": "PASS", "alpha": {"status": "PASS"},
                          "counter": {"status": "NOT_EVALUATED", "value_modulo_256": None}}}
    return {"scope": "owned_cef_smoke_fixture", "native_host_executed": True,
            "native_host_execution_attempted": True, "expected_executable_sha256": "a" * 64,
            "native_generation": 7, "requested": dict(cycles.REQUESTED),
            "static_inventory": {"status": "PASS"}, "credential_backend": "chromium-use-mock-keychain",
            "supervision": supervision, "samples": samples, **cycles.launcher.classify(supervision, samples)}


class NativeCycleTests(unittest.TestCase):
    def test_counter_not_visible_is_preserved_without_blocking_lifecycle(self):
        report = fixture_report()
        self.assertEqual(report["status"], "PARTIAL")
        result = cycles.assess_report(report, "a" * 64, 7, 1)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["visible_counter_changed"], "NOT_EVALUATED")
        self.assertIsNone(result["counter_delta_modulo_256"])
        self.assertIsNone(result["counter_observations"]["latest"]["value_modulo_256"])

    def test_each_required_failure_stops_before_next_launch(self):
        def frame(report): report["samples"]["latest"]["status"] = "FAIL"
        def alpha(report): report["samples"]["latest"]["alpha"]["status"] = "FAIL"
        def shutdown(report): report["supervision"].update(reason="deadline", returncode=-15)
        def cleanup(report): report["supervision"]["final_remaining_observed_pids"] = [123]
        for failure in (frame, alpha, shutdown, cleanup):
            with self.subTest(failure=failure.__name__):
                calls, snapshots = [], []
                def run_one(index):
                    calls.append(index)
                    report = fixture_report()
                    if index == 2:
                        failure(report)
                        report.update(cycles.launcher.classify(report["supervision"], report["samples"]))
                    return cycles.assess_report(report, "a" * 64, 7, 1)
                result = cycles.run_sequence(100, 600, run_one, lambda r: snapshots.append(deepcopy(r)), clock=lambda: 0)
                self.assertEqual(calls, [1, 2])
                self.assertEqual(result["passed_cycles"], 1)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["stop_reason"], "CYCLE_FAILED")
                self.assertTrue(any(r.get("active_cycle") == 2 for r in snapshots))

    def test_static_or_native_identity_errors_cannot_be_counter_exceptions(self):
        for key, value in [("native_host_executed", False), ("native_generation", 6),
                           ("expected_executable_sha256", "b" * 64), ("credential_backend", None),
                           ("scope", "static_preflight_only"), ("error", {"code": "FAILED"}),
                           ("status", "PASS")]:
            with self.subTest(key=key):
                report = fixture_report()
                report[key] = value
                self.assertEqual(cycles.assess_report(report, "a" * 64, 7, 1)["status"], "FAIL")
        self.assertEqual(cycles.assess_report(fixture_report(), "a" * 64, 7, 0)["status"], "FAIL")

    def test_report_gates_cannot_hide_underlying_shutdown_failure(self):
        report = fixture_report()
        report["supervision"].update(reason="deadline", returncode=-15)
        result = cycles.assess_report(report, "a" * 64, 7, 1)
        self.assertEqual(result["gates"]["orderly_shutdown"], "FAIL")
        self.assertFalse(result["launcher_result_consistent"])
        self.assertEqual(result["status"], "FAIL")

    def test_budget_stops_admission_and_does_not_claim_all_cycles(self):
        now, calls = [0], []
        def run_one(index):
            calls.append(index)
            now[0] += 20
            return {"status": "PASS", "native_host_executed": True}
        result = cycles.run_sequence(100, 60, run_one, lambda _: None, clock=lambda: now[0])
        self.assertEqual(calls, [1])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["stop_reason"], "TIME_BUDGET_NO_NEW_LAUNCH")

    def test_report_error_stops_and_keeps_execution_unknown(self):
        calls = []
        def run_one(index):
            calls.append(index)
            raise ValueError("TEST_REPORT_MISSING")
        result = cycles.run_sequence(100, 600, run_one, lambda _: None, clock=lambda: 0)
        self.assertEqual(calls, [1])
        self.assertEqual(result["native_process_runs_unknown"], 1)
        self.assertEqual(result["native_process_runs_observed"], 0)
        self.assertEqual(result["cycles"][0]["error_code"], "TEST_REPORT_MISSING")


if __name__ == "__main__":
    unittest.main()
