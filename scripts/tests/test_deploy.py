import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('deploy', Path(__file__).parents[1] / 'deployment/deploy.py')
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)
SHA = 'a' * 40


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.calls = []
        self.failure = None
        self.bad_version = False
        self.config = patch.dict(os.environ, {
            'DEPLOY_SOURCE': str(self.root), 'DEPLOY_STATE': str(self.root / 'state'),
            'DEPLOY_COMPOSE': str(self.root / 'compose.yml'), 'DEPLOY_URL': 'https://example.org',
        })
        self.config.start()
        self.addCleanup(self.config.stop)

    def run_command(self, *args, **kwargs):
        self.calls.append(tuple(map(str, args)))
        if args[0] == 'tar':
            (Path(args[-1]) / 'web/public').mkdir(parents=True)
        if self.failure and self.failure(args):
            raise subprocess.CalledProcessError(1, args)

    def response(self, url, **kwargs):
        data = {'status': 'alive'} if '/health/live' in url else {'sha': 'wrong' if self.bad_version else SHA}
        return io.StringIO(json.dumps(data))

    def execute(self):
        with patch.object(deploy, 'run', side_effect=self.run_command), \
             patch.object(deploy, 'output', side_effect=lambda *args: SHA if args[0] == 'git' else 'sha256:previous'), \
             patch.object(deploy.urllib.request, 'urlopen', side_effect=self.response), \
             patch.object(deploy.time, 'sleep'):
            deploy.main()

    def test_success_records_verified_commit_and_updates_only_web(self):
        self.execute()
        record = json.loads((self.root / 'state/deployed.json').read_text())
        self.assertEqual(record['sha'], SHA)
        activations = [c for c in self.calls if c[:2] == ('docker', 'compose')]
        self.assertEqual(len(activations), 1)
        self.assertEqual(activations[0][-1], 'web')
        self.assertIn('--no-deps', activations[0])
        self.assertFalse(any('reset' in c for c in self.calls))

    def test_unchanged_revision_skips_build(self):
        self.execute()
        self.calls.clear()
        self.execute()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], 'git')

    def test_failed_tests_do_not_replace_live_container(self):
        self.failure = lambda args: args[:2] == ('docker', 'run')
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute()
        self.assertFalse(any(c[:2] == ('docker', 'compose') for c in self.calls))
        self.assertFalse((self.root / 'state/deployed.json').exists())

    def test_failed_public_verification_rolls_back(self):
        self.bad_version = True
        with self.assertRaises(RuntimeError):
            self.execute()
        activations = [c for c in self.calls if c[:2] == ('docker', 'compose')]
        self.assertEqual(len(activations), 2)
        self.assertFalse((self.root / 'state/deployed.json').exists())

    def test_failed_activation_rolls_back(self):
        attempts = []
        def fail_first_activation(args):
            if args[:2] == ('docker', 'compose'):
                attempts.append(args)
                return len(attempts) == 1
            return False
        self.failure = fail_first_activation
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute()
        self.assertEqual(len(attempts), 2)
        self.assertFalse((self.root / 'state/deployed.json').exists())

    def test_missing_old_image_is_snapshotted_before_release(self):
        self.failure = lambda args: args[:2] == ('docker', 'tag')
        self.execute()
        self.assertIn(('docker', 'commit', 'rotterdam_live_web', 'rotterdam_live_web:rollback'), self.calls)
