"""Maintain only an isolated heartbeat branch, never source or market data."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BRANCH = 'maintenance/keepalive'
REPOSITORY = 'blizzardoner/etf-atlas'


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, text=True, encoding='utf-8', capture_output=True)
    if result.returncode:
        raise RuntimeError('Keepalive git operation failed: ' + args[0])
    return result.stdout.strip()


def maintain(root, allowed_origins, now=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    if git(root, 'remote', 'get-url', 'origin') not in allowed_origins:
        raise ValueError('Unexpected keepalive repository origin')
    if git(root, 'branch', '--show-current') != 'main' or git(root, 'status', '--porcelain'):
        raise ValueError('Keepalive requires an isolated clean main checkout')
    if git(root, 'ls-remote', '--heads', 'origin', 'refs/heads/' + BRANCH):
        git(root, 'fetch', 'origin', 'refs/heads/' + BRANCH)
        git(root, 'checkout', '-B', BRANCH, 'FETCH_HEAD')
    else:
        git(root, 'switch', '--orphan', BRANCH)
    git(root, 'config', 'user.name', 'github-actions[bot]')
    git(root, 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    body = {'repository': REPOSITORY, 'checkedAt': now.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'), 'purpose': 'Keep daily ETF update schedules active; no prices or source changes.'}
    (root / 'heartbeat.json').write_text(json.dumps(body, indent=2) + '\n', encoding='utf-8')
    git(root, 'add', '--', 'heartbeat.json')
    if git(root, 'diff', '--cached', '--name-only').splitlines() != ['heartbeat.json']:
        raise ValueError('Keepalive must not stage source or market data')
    git(root, 'commit', '-m', 'chore: keep scheduled ETF updates active')
    if git(root, 'ls-tree', '--name-only', 'HEAD').splitlines() != ['heartbeat.json']:
        raise ValueError('Unexpected files in keepalive branch')
    git(root, 'push', 'origin', 'HEAD:refs/heads/' + BRANCH)
    return {**body, 'branch': BRANCH, 'commit': git(root, 'rev-parse', 'HEAD')}


def main(environ=None):
    import os
    env = os.environ if environ is None else environ
    if (env.get('GITHUB_ACTIONS') != 'true' or env.get('GITHUB_REPOSITORY') != REPOSITORY
            or env.get('GITHUB_REF') != 'refs/heads/main'):
        print('Keepalive is restricted to this repository in GitHub Actions on main')
        return 1
    root = Path(__file__).resolve().parents[1]
    if not env.get('GITHUB_WORKSPACE') or Path(env['GITHUB_WORKSPACE']).resolve() != root:
        print('Unexpected keepalive workspace')
        return 1
    origins = ('https://github.com/' + REPOSITORY, 'https://github.com/' + REPOSITORY + '.git')
    try:
        result = maintain(root, origins)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
