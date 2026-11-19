"""Checker regressions use controlled metadata or copies of retained evidence.

These tests launch no browser and create no purported native evidence.
"""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('h19_lifecycle_check', Path(__file__).resolve().parents[1] / 'tools/h19_lifecycle_check.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
MS = CHECK.NS_MS


def trace(**phases):
    return [{'phase': name, 'observed_ns': value} for name, value in phases.items()]


def frames():
    stats = dict(paints=5, pending=0, leased=0, coalesced=2, stale=0, consumed=2,
                 released_unconsumed=0, invalidated_close=1, revoked_generation=0,
                 acquired=3, retained_leases=0, retained_bytes=0)
    return dict(accounting_v2=stats, paints=5, acquired=3, coalesced=2, stale=0,
                samples=[[2, 10, 11, 1], [4, 20, 21, 1]], samples_truncated=False)


def resized():
    old = dict(identity=(1, 1, 1), trace=trace(resize_requested=1000 * MS),
               epoch=dict(epoch=1, width=640, height=360, revocation='epoch', ended_ns=1010 * MS),
               times=[900 * MS, 990 * MS])
    new = dict(identity=(1, 1, 2), trace=trace(resize_epoch_started=1020 * MS),
               epoch=dict(epoch=2, width=540, height=960, started_ns=1010 * MS,
                          first_paint_ns=1100 * MS), times=[1100 * MS, 1200 * MS])
    return old, new


def recovered():
    old = dict(manifest=dict(instance=1, generation=1, browser_id=1, closed_ns=120,
                            renderer_exit_code=22016, renderer_pid_reported=100, failed=True),
               trace=trace(renderer_exit_requested=100, renderer_terminated=110, before_close=120))
    new = dict(manifest=dict(instance=1, generation=2, browser_id=2,
                            renderer_pid_reported=101, failed=False),
               trace=trace(create_requested=130, after_created=140),
               epoch=dict(epoch=1, first_paint_ns=150))
    return old, new


class Accounting(unittest.TestCase):
    def test_exact_accounting_and_complete_sample_coverage(self):
        self.assertEqual(CHECK.conservation(frames())['terminal_sum'], 5)
        for field in ('consumed', 'coalesced', 'invalidated_close'):
            data = frames()
            data['accounting_v2'][field] += 1
            with self.assertRaisesRegex(CHECK.EvidenceError, 'PAINT_CONSERVATION'):
                CHECK.conservation(data)

    def test_retained_bytes_and_lease_cannot_be_promoted_by_terminal_counts(self):
        for field in ('retained_bytes', 'retained_leases'):
            data = frames()
            data['accounting_v2'][field] = 1
            with self.assertRaisesRegex(CHECK.EvidenceError, 'RETAINED_AFTER_JOIN'):
                CHECK.conservation(data)

    def test_incomplete_reordered_or_missing_samples_are_not_complete_evidence(self):
        data = frames()
        data['samples_truncated'] = True
        with self.assertRaisesRegex(CHECK.EvidenceError, 'INCOMPLETE_SAMPLE_COVERAGE'):
            CHECK.conservation(data)
        data = frames()
        data['samples'].reverse()
        with self.assertRaisesRegex(CHECK.EvidenceError, 'SAMPLE_ORDER'):
            CHECK.conservation(data)
        data = frames()
        data['samples'].pop()
        with self.assertRaisesRegex(CHECK.EvidenceError, 'CONSUMED_SAMPLE_COVERAGE'):
            CHECK.conservation(data)


class NativeIntervals(unittest.TestCase):
    def test_hidden_requires_observed_gap_resume_and_continuous_peers(self):
        begin, end = 1000 * MS, 5000 * MS
        target = [900 * MS, 990 * MS, 5020 * MS, 5100 * MS]
        peers = {2: list(range(begin, end + 1, 50 * MS))}
        result = CHECK.interruption(target, peers, begin, end, 3000)
        self.assertGreaterEqual(result['target_paint_gap_ms'], 3000)
        with self.assertRaisesRegex(CHECK.EvidenceError, 'TARGET_PAINT_DURING_SETTLED_INTERVAL'):
            CHECK.interruption(target + [2000 * MS], peers, begin, end, 3000)
        with self.assertRaisesRegex(CHECK.EvidenceError, 'PEER_FRAME_OBSERVATIONS_MISSING'):
            CHECK.interruption(target, {2: []}, begin, end, 3000)
        with self.assertRaisesRegex(CHECK.EvidenceError, 'TARGET_BEFORE_AFTER_OBSERVATIONS'):
            CHECK.interruption([], peers, begin, end, 3000)

    def test_resize_rejects_stale_epoch_geometry_and_one_second_latency(self):
        old, new = resized()
        self.assertEqual(CHECK.resize_check(old, new)['latency_ms'], 100)
        wrong = copy.deepcopy(new)
        wrong['identity'] = (2, 1, 2)
        with self.assertRaisesRegex(CHECK.EvidenceError, 'RESIZE_IDENTITY'):
            CHECK.resize_check(old, wrong)
        late = copy.deepcopy(new)
        late['epoch']['first_paint_ns'] = 2000 * MS
        with self.assertRaisesRegex(CHECK.EvidenceError, 'RESIZE_FIRST_PAINT_LATENCY'):
            CHECK.resize_check(old, late)
        old['times'].append(1050 * MS)
        with self.assertRaisesRegex(CHECK.EvidenceError, 'OLD_EPOCH_ACCEPTED_AFTER_RESIZE'):
            CHECK.resize_check(old, new)

    def test_recovery_requires_encoded_exit_new_generation_and_real_final_close(self):
        old, new = recovered()
        self.assertEqual(CHECK.replacement_check(old, new, 'renderer_exit_requested')['decoded_exit_code'], 86)
        bad = copy.deepcopy(old)
        bad['manifest']['renderer_exit_code'] = 86
        with self.assertRaisesRegex(CHECK.EvidenceError, 'CONTROLLED_RENDERER_EXIT_CODE'):
            CHECK.replacement_check(bad, new, 'renderer_exit_requested')
        bad = copy.deepcopy(new)
        bad['trace'][0]['observed_ns'] = 115
        with self.assertRaisesRegex(CHECK.EvidenceError, 'REPLACEMENT_NATIVE_ORDER'):
            CHECK.replacement_check(old, bad, 'renderer_exit_requested')
        bad = copy.deepcopy(new)
        bad['manifest']['browser_id'] = 1
        with self.assertRaisesRegex(CHECK.EvidenceError, 'REPLACEMENT_BROWSER_REUSED'):
            CHECK.replacement_check(old, bad, 'renderer_exit_requested')

    def test_phase_trace_repetition_is_not_a_single_completion(self):
        rows = trace(before_close=100)
        rows += trace(before_close=101)
        with self.assertRaisesRegex(CHECK.EvidenceError, 'PHASE_EXACTLY_ONCE'):
            CHECK.phase(rows, 'before_close')


class TargetedEvents(unittest.TestCase):
    def fixture(self):
        return {identity: [dict(events_received=24 if identity == 1 else 0,
                _trace=([{'phase': 'fixture_event_dispatched'}, {'phase': 'fixture_event_received'}] * 24)
                if identity == 1 else [])] for identity in (1, 2, 3)}

    def test_twenty_four_events_only_for_one_instance(self):
        self.assertEqual(CHECK.targeted_events(self.fixture())['instances']['1']['received'], 24)
        data = self.fixture()
        data[2][0]['events_received'] = 1
        data[2][0]['_trace'] = [{'phase': 'fixture_event_dispatched'}, {'phase': 'fixture_event_received'}]
        with self.assertRaisesRegex(CHECK.EvidenceError, 'EVENT_TARGET_CONTAMINATION_OR_LOSS'):
            CHECK.targeted_events(data)

    def test_manifest_count_does_not_replace_observed_delivery_trace(self):
        data = self.fixture()
        data[1][0]['_trace'].pop()
        with self.assertRaisesRegex(CHECK.EvidenceError, 'EVENT_TARGET_CONTAMINATION_OR_LOSS'):
            CHECK.targeted_events(data)


class EvidenceInputs(unittest.TestCase):
    def test_duplicate_nonfinite_and_ambiguous_json_are_rejected(self):
        for data in ('{"count":1,"count":2}', '{"count":NaN}', '{"count":Infinity}'):
            with self.assertRaises(CHECK.EvidenceError):
                CHECK.strict_json(data)

    def test_read_limits_traversal_and_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'file').write_bytes(b'actual')
            (root / 'link').symlink_to(root / 'file')
            (root / 'compressed').write_bytes(gzip.compress(b'x' * 1000))
            reader = CHECK.Inputs(root)
            with self.assertRaisesRegex(CHECK.EvidenceError, 'INPUT_SYMLINK'):
                reader.read('link')
            with self.assertRaisesRegex(CHECK.EvidenceError, 'INPUT_PATH'):
                reader.read('../file')
            with self.assertRaisesRegex(CHECK.EvidenceError, 'DECOMPRESSED_SIZE'):
                reader.read('compressed', maximum=100, compressed=True)
            self.assertEqual(reader.read('file'), b'actual')
            self.assertIn('file', reader.hashes)

    def test_nested_run_resolves_build_report_from_lab_not_run_depth(self):
        # Deliberately incomplete synthetic evidence stops at INSTANCE_COUNT;
        # reaching that guard proves build provenance resolved at both depths.
        with tempfile.TemporaryDirectory() as temporary:
            lab = Path(temporary)
            (lab / 'evidence').mkdir()
            build = json.dumps({'binaries': [{'path': '.cache/app/Contents/MacOS/MotiveBrowserFixture',
                                             'sha256': 'a' * 64}]}).encode()
            (lab / 'evidence/build.json').write_bytes(build)
            raw_supervision = b'{}'
            compressed = gzip.compress(raw_supervision)
            report = {'native_host_executed': True, 'production_connected': False,
                      'supervision_gzip_sha256': hashlib.sha256(compressed).hexdigest(),
                      'supervision_sha256': hashlib.sha256(raw_supervision).hexdigest(),
                      'build_report': 'evidence/build.json',
                      'build_report_sha256': hashlib.sha256(build).hexdigest(),
                      'expected_executable_sha256': 'a' * 64}
            for name in ('direct', 'suite/nested'):
                run = lab / 'evidence' / name
                run.mkdir(parents=True)
                (run / 'instances.json').write_text(json.dumps({'native_executed': True,
                    'third_party_execution': False, 'scenario': 'lifecycle', 'host_pid': 100, 'instances': []}))
                (run / 'report.json').write_text(json.dumps(report))
                (run / 'supervision.json.gz').write_bytes(compressed)
                (run / 'lifecycle.jsonl').write_text('{"phase":"initialize_enter","observed_ns":1}\n')
                with patch.object(CHECK, 'LAB_ROOT', lab):
                    result = CHECK.analyze(run)
                self.assertEqual(result['gates']['evidence_structure']['reason'], 'INSTANCE_COUNT')
                self.assertEqual(result['build_report']['sha256'], hashlib.sha256(build).hexdigest())

    def test_summary_pass_without_raw_native_files_never_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'report.json').write_text(json.dumps({'status': 'PASS', 'gates': {'everything': 'PASS'}}))
            result = CHECK.analyze(root)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['gates']['evidence_structure']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
