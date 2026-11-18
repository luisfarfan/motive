"""Interpreter selection/provenance tests with fake probes, no subprocess execution."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from verification_python import PILLOW_SUITES, PILLOW_VERSION, verification_python
import verify_h14_beta as beta


class VerificationPythonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='motive-python-preflight-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.venv = self.root / 'existing-venv'
        (self.venv / 'bin').mkdir(parents=True)
        self.binary = self.root / 'system-python'
        self.binary.write_text('unit fixture, never executed')
        self.binary.chmod(0o700)
        self.python = self.venv / 'bin/python'
        self.python.symlink_to(self.binary)
        self.metadata = {'executable': str(self.python), 'prefix': str(self.venv),
                         'base_prefix': str(self.root / 'base-python'), 'version': '3.14.7 unit fixture',
                         'pillow_version': PILLOW_VERSION,
                         'pillow_file': str(self.venv / 'lib/python3.14/site-packages/PIL/__init__.py')}

    def probe(self, metadata=None, **kwargs):
        response = SimpleNamespace(returncode=0, stdout=json.dumps(metadata or self.metadata), stderr='')
        return patch('verification_python.subprocess.run', return_value=response, **kwargs)

    def test_legacy_subset_never_probes_or_requires_the_missing_default_venv(self):
        with patch('verification_python.subprocess.run') as run:
            result = verification_python(self.root, ['verify_control.py', 'verify_control_delivery.py'])
        run.assert_not_called()
        self.assertEqual(result['status'], 'NOT_REQUIRED')
        self.assertFalse((self.root / 'var/verify-python').exists())

    def test_explicit_symlink_interpreter_is_forwarded_without_resolving_it(self):
        with self.probe() as run:
            result = verification_python(self.root, ['verify_h11_runtime.py'], self.python)
        self.assertEqual(run.call_args.args[0][:4], [str(self.python), '-I', '-B', '-c'])
        self.assertNotEqual(run.call_args.args[0][0], str(self.binary))
        self.assertEqual(result['requested'], str(self.python))
        self.assertEqual(result['prefix'], str(self.venv))
        self.assertEqual(result['pillow_version'], '12.0.0')
        self.assertEqual(run.call_args.kwargs['timeout'], 10)

    def test_alias_to_existing_venv_retains_venv_in_argv(self):
        alias = self.root / 'h13-venv'
        alias.symlink_to(self.venv, target_is_directory=True)
        selected = alias / 'bin/python'
        with self.probe() as run:
            result = verification_python(self.root, ['verify_h12_performance.py'], selected)
        self.assertEqual(run.call_args.args[0][0], str(selected))
        self.assertEqual(result['status'], 'VERIFIED')

    def test_default_path_is_preserved_and_full_suite_requires_preflight(self):
        default = self.root / 'var/verify-python'
        default.parent.mkdir()
        default.symlink_to(self.venv, target_is_directory=True)
        with self.probe() as run:
            result = verification_python(self.root, [])
        self.assertEqual(run.call_args.args[0][0], str(default / 'bin/python'))
        self.assertEqual(result['status'], 'VERIFIED')

    def test_invalid_paths_fail_before_a_probe(self):
        for path in ('relative/python', self.root / 'missing', self.root / 'a/../existing-venv/bin/python'):
            with self.subTest(path=path), patch('verification_python.subprocess.run') as run:
                with self.assertRaises(ValueError):
                    verification_python(self.root, ['verify_h11_runtime.py'], path)
                run.assert_not_called()

    def test_missing_pillow_wrong_version_global_package_and_wrong_prefix_reject(self):
        cases = [dict(self.metadata, pillow_version='11.0.0'),
                 dict(self.metadata, pillow_file=str(self.root / 'global/PIL/__init__.py')),
                 dict(self.metadata, prefix=self.metadata['base_prefix']),
                 dict(self.metadata, prefix=str(self.root / 'other-venv'))]
        for metadata in cases:
            with self.subTest(metadata=metadata), self.probe(metadata):
                with self.assertRaises(ValueError):
                    verification_python(self.root, ['verify_h11_runtime.py'], self.python)
        with patch('verification_python.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='ImportError')):
            with self.assertRaises(ValueError):
                verification_python(self.root, ['verify_h11_runtime.py'], self.python)

    def test_probe_timeout_does_not_fall_back_to_global_python(self):
        with patch('verification_python.subprocess.run', side_effect=subprocess.TimeoutExpired('unit fixture', 10)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                verification_python(self.root, ['verify_h11_runtime.py'], self.python)
        self.assertEqual(run.call_count, 1)

    def test_requirements_and_wrapper_groups_match_without_importing_runner(self):
        scripts = Path(__file__).resolve().parent
        required = (scripts / 'requirements-h11.txt').read_text().splitlines()
        self.assertIn('Pillow==' + PILLOW_VERSION, required)
        tree = ast.parse((scripts / 'verify_h13_regressions.py').read_text())
        suites = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in
                    ('OVERLAYS', 'PERFORMANCE') for target in node.targets):
                suites.extend(ast.literal_eval(node.value))
        self.assertEqual(set(suites), set(PILLOW_SUITES))

    def test_coordinator_forwards_explicit_path_to_regression_wrapper(self):
        args = SimpleNamespace(stage='regressions', app=Path('/test/Motive.app/Contents/MacOS/motive'),
                               data_root=self.root / 'data', verification_python=self.python,
                               suite=['verify_h11_runtime.py'], camera_id=None,
                               camera_prepared=False, microphone_id=None)
        command = beta.commands(args, self.root / 'output')[0]
        index = command.index('--verification-python')
        self.assertEqual(command[index + 1], str(self.python))
        self.assertNotEqual(command[index + 1], str(self.binary))
        args.verification_python = None
        self.assertNotIn('--verification-python', beta.commands(args, self.root / 'output')[0])


if __name__ == '__main__':
    unittest.main()
