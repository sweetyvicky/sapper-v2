"""Real isolated Linux acceptance for persistent local Mock exercise."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'examples/pentest/local_legion.py'

@unittest.skipUnless(sys.platform == 'linux', 'Linux broker boundary integration')
class LocalLegionTests(unittest.TestCase):
    def invoke(self, command, state, artifacts, *extra):
        return subprocess.run([sys.executable, '-W', 'error::ResourceWarning', str(ENTRY), command,
            '--state', str(state), '--artifacts', str(artifacts), *extra], capture_output=True, text=True, timeout=45)

    def test_persistent_prepare_exercise_and_consumed_rejection(self):
        self.assertTrue(ENTRY.is_file(), 'persistent scenario entrypoint is missing')
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state'
            artifacts = Path(directory) / 'artifacts'
            prepared = self.invoke('prepare', state, artifacts)
            self.assertEqual(prepared.returncode, 0, prepared.stderr + prepared.stdout)
            policy = json.loads((state / 'policy.json').read_text())
            self.assertEqual(policy['allowed_origins'], ['http://127.0.0.1:18080'])
            self.assertEqual(policy['budget'], dict(requests=8, bytes=8000, seconds=32, parallel=1))
            self.assertNotEqual(self.invoke('prepare', state, artifacts).returncode, 0)
            exercised = self.invoke('exercise', state, artifacts, '--pace-seconds', '0')
            self.assertEqual(exercised.returncode, 0, exercised.stderr + exercised.stdout)
            summary = json.loads((artifacts / 'summary.json').read_text())
            self.assertTrue(summary['exercise_complete'])
            self.assertFalse(summary['engagement_complete'])
            self.assertTrue(all(summary['assertions'].values()), summary)
            self.assertEqual(summary['fixture_hits'], 4)
            self.assertEqual(set(summary['role_results']), {'Scout', 'Soldier', 'General'})
            self.assertTrue(all(r['status'] == 'succeeded' for r in summary['role_results'].values()))
            self.assertTrue(summary['synthetic_manual_decision'])
            self.assertEqual(summary['bounded_stop_reason'], 'step_limit')
            self.assertEqual(summary['final_stop_reason'], 'blocked')
            html = (artifacts / 'coverage-demo.html').read_text()
            self.assertIn('coverage-data', html)
            self.assertNotIn('PRIVATE_RESPONSE_BODY', html)
            files = {str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()}
            again = self.invoke('exercise', state, artifacts, '--pace-seconds', '0')
            self.assertNotEqual(again.returncode, 0)
            self.assertIn('already', again.stdout)
            self.assertEqual(files, {str(p.relative_to(state)): p.read_bytes() for p in state.rglob('*') if p.is_file()})
            self.assertEqual(summary, json.loads((artifacts / 'summary.json').read_text()))
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(('127.0.0.1', 18080)), 0)
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', 18080))

    def test_bad_pace_rejected_before_consumption(self):
        self.assertTrue(ENTRY.is_file(), 'persistent scenario entrypoint is missing')
        with tempfile.TemporaryDirectory() as directory:
            state, artifacts = Path(directory)/'state', Path(directory)/'artifacts'
            self.assertEqual(self.invoke('prepare', state, artifacts).returncode, 0)
            for pace in ('-1', '4', 'nan'):
                self.assertNotEqual(self.invoke('exercise', state, artifacts, '--pace-seconds', pace).returncode, 0)
            self.assertFalse((state/'exercise-started.json').exists())


    def test_export_failure_preserves_state_without_success_and_closes_fixture(self):
        self.assertTrue(ENTRY.is_file(), 'persistent scenario entrypoint is missing')
        with tempfile.TemporaryDirectory() as directory:
            state, artifacts = Path(directory)/'state', Path(directory)/'artifacts'
            self.assertEqual(self.invoke('prepare', state, artifacts).returncode, 0)
            (artifacts/'status.json').mkdir()
            failed = self.invoke('exercise', state, artifacts, '--pace-seconds', '0')
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(json.loads(failed.stdout)['exercise_complete'])
            self.assertTrue((state/'exercise-started.json').is_file())
            self.assertTrue((state/'ledger.sqlite').is_file())
            self.assertFalse((artifacts/'summary.json').exists(), 'failure must not leave a success summary')
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(('127.0.0.1',18080)), 0)
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1',18080))
