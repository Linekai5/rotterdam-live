import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'check-public-tree.py'
spec = importlib.util.spec_from_file_location('public_tree', SCRIPT)
public_tree = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_tree)


class PublicTreeTests(unittest.TestCase):
    def test_documentation_addresses_include_loopback_and_ipv6(self):
        for address in ('127.0.0.1', '192.0.2.10', '::1', '2001:db8::42', '::ffff:192.0.2.10'):
            with self.subTest(address=address):
                self.assertTrue(public_tree.check_text('README.md', f'Host: [{address}]'))
        self.assertFalse(public_tree.check_text('README.md', 'Host: localhost; revision 2.7.0'))
        self.assertFalse(public_tree.check_text('vite.config.js', '127.0.0.1'))

    def test_private_values_fail_without_printing_them(self):
        values = (
            'ghp_' + 'x' * 36,
            '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----',
            'postgresql://user:' + 'private-value@localhost/db',
            '${POSTGRES_' + 'PASSWORD:-private-value}',
            'POSTGRES_PASSWORD: ' + 'private-value',
        )
        for value in values:
            with self.subTest(value_type=value[:5]):
                findings = public_tree.check_text('config.yml', value)
                self.assertTrue(findings)
                self.assertNotIn('private-value', '\n'.join(findings))

    def test_environment_placeholders_and_blank_examples_are_allowed(self):
        for value in (
            'POSTGRES_PASSWORD=',
            'POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set it privately}',
            'postgresql://user:${POSTGRES_PASSWORD}@db/example',
            '${PUBLIC_BIND_ADDRESS}:80:80',
        ):
            self.assertFalse(public_tree.check_text('.env.example', value))

    def test_forced_tracking_of_backend_and_env_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / '.gitignore').write_text('/api/\n.env.*\n!.env.example\n')
            (root / 'api').mkdir()
            (root / 'api' / 'private.py').write_text('# private backend\n')
            (root / '.env.production').write_text('EXAMPLE=private\n')
            (root / '.env.example').write_text('POSTGRES_PASSWORD=\n')
            subprocess.run(['git', 'add', '-f', '.'], cwd=root, check=True)
            result = subprocess.run(['python3', str(SCRIPT)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('api/private.py: private path is tracked', result.stdout)
            self.assertIn('.env.production: tracked file matches an ignore rule', result.stdout)
            self.assertNotIn('.env.example:', result.stdout)


if __name__ == '__main__':
    unittest.main()
