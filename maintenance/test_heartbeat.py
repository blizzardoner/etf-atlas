import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone

MODULE = pathlib.Path(__file__).with_name('heartbeat.py')

class HeartbeatTests(unittest.TestCase):
    def module(self):
        self.assertTrue(MODULE.exists(), 'scheduled update keepalive is missing')
        spec = importlib.util.spec_from_file_location('heartbeat', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def git(self, root, *args):
        return subprocess.check_output(['git', *args], cwd=root, text=True, encoding='utf-8', stderr=subprocess.DEVNULL).strip()

    def fixture(self, root):
        remote = root / 'remote.git'
        work = root / 'work'
        self.git(root, 'init', '--bare', remote.as_posix())
        work.mkdir()
        self.git(work, 'init', '-b', 'main')
        self.git(work, 'config', 'user.name', 'Fixture')
        self.git(work, 'config', 'user.email', 'fixture@example.invalid')
        (work / 'main.txt').write_text('main remains unchanged', encoding='utf-8')
        self.git(work, 'add', 'main.txt')
        self.git(work, 'commit', '-m', 'fixture')
        self.git(work, 'remote', 'add', 'origin', remote.as_posix())
        self.git(work, 'push', 'origin', 'main')
        return work, remote

    def test_heartbeat_is_an_isolated_repository_activity_without_main_changes(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as folder:
            work, remote = self.fixture(pathlib.Path(folder))
            main = self.git(work, 'rev-parse', 'main')
            result = module.maintain(work, (remote.as_posix(),), datetime(2026, 11, 21, tzinfo=timezone.utc))
            self.assertEqual(self.git(work, 'rev-parse', 'main'), main)
            self.assertEqual(self.git(work, 'ls-tree', '--name-only', 'HEAD'), 'heartbeat.json')
            self.assertEqual(self.git(remote, 'rev-parse', 'main'), main)
            self.assertEqual(self.git(remote, 'rev-parse', 'maintenance/keepalive'), result['commit'])
            self.assertEqual(json.loads(self.git(remote, 'show', 'maintenance/keepalive:heartbeat.json'))['checkedAt'], '2026-11-21T00:00:00Z')

    def test_next_month_updates_existing_heartbeat_only(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as folder:
            work, remote = self.fixture(pathlib.Path(folder))
            main = self.git(work, 'rev-parse', 'main')
            first = module.maintain(work, (remote.as_posix(),), datetime(2026, 11, 21, tzinfo=timezone.utc))
            self.git(work, 'checkout', 'main')
            second = module.maintain(work, (remote.as_posix(),), datetime(2026, 12, 1, tzinfo=timezone.utc))
            self.assertNotEqual(first['commit'], second['commit'])
            self.assertEqual(self.git(work, 'rev-parse', 'HEAD~1'), first['commit'])
            self.assertEqual(self.git(remote, 'rev-parse', 'main'), main)
            self.assertEqual(self.git(remote, 'ls-tree', '--name-only', 'maintenance/keepalive'), 'heartbeat.json')

    def test_unsafe_origins_branches_and_dirty_workspaces_are_refused_before_writes(self):
        module = self.module()
        for scenario in ['origin', 'branch', 'dirty']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                work, remote = self.fixture(pathlib.Path(folder))
                allowed = (remote.as_posix(),)
                if scenario == 'origin':
                    allowed = ('different-origin',)
                elif scenario == 'branch':
                    self.git(work, 'checkout', '-b', 'feature')
                else:
                    (work / 'notes.txt').write_text('not automation-owned', encoding='utf-8')
                before = self.git(work, 'rev-parse', 'HEAD')
                with self.assertRaises(ValueError):
                    module.maintain(work, allowed)
                self.assertEqual(self.git(work, 'rev-parse', 'HEAD'), before)
                self.assertTrue((work / 'main.txt').exists())
                self.assertEqual(self.git(remote, 'ls-remote', '--heads', remote.as_posix(), 'refs/heads/maintenance/keepalive'), '')

    def test_cli_refuses_non_ci_other_repositories_and_feature_branches(self):
        from unittest.mock import patch
        module = self.module()
        self.assertTrue(hasattr(module, 'main'), 'CI-only keepalive entry is missing')
        for env in [{}, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'other/repo', 'GITHUB_REF': 'refs/heads/main'}, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'blizzardoner/etf-atlas', 'GITHUB_REF': 'refs/heads/feature'}]:
            with self.subTest(env=env), patch.object(module, 'maintain') as maintain:
                self.assertEqual(module.main(env), 1)
                maintain.assert_not_called()

if __name__ == '__main__':
    unittest.main()
