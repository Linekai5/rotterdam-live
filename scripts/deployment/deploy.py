#!/usr/bin/env python3
"""Trusted host entrypoint: deploy main's frontend without checking out private files."""
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request


def run(*args, **kwargs):
    print('+', *map(str, args), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def output(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


def read_status(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def publish_github_status(sha, status, description):
    repository = os.environ.get('DEPLOY_GITHUB_REPOSITORY')
    if not repository:
        return False
    try:
        subprocess.run([
            'gh', 'api', '--method', 'POST', f'repos/{repository}/statuses/{sha}',
            '-f', f'state={status}', '-f', 'context=Production deployment',
            '-f', f'description={description}',
            '-f', f'target_url={os.environ["DEPLOY_URL"].rstrip("/")}/version.json',
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        return True
    except (OSError, subprocess.SubprocessError):
        print('Could not publish GitHub deployment status; local status is retained.', flush=True)
        return False


def report_status(state, sha, status, description):
    path = state / 'status.json'
    previous = read_status(path)
    same = all(previous.get(key) == value for key, value in
               {'sha': sha, 'state': status, 'description': description}.items())
    if same and (previous.get('github_published') or not os.environ.get('DEPLOY_GITHUB_REPOSITORY')):
        return
    published = publish_github_status(sha, status, description)
    record = {'sha': sha, 'state': status, 'description': description,
              'updated_at': datetime.now(timezone.utc).isoformat(), 'github_published': published}
    pending = state / 'status.tmp'
    pending.write_text(json.dumps(record) + '\n')
    pending.replace(path)


def failure_description(error):
    if isinstance(error, subprocess.CalledProcessError):
        command = error.cmd
        if 'scripts/check-live-weather.mjs' in command:
            return 'Weather API compatibility check failed; previous release kept.'
        if 'build' in command:
            return 'Frontend build failed; previous release kept.'
        if 'npm' in command and 'test' in command:
            return 'Frontend tests failed; previous release kept.'
    return 'Deployment failed; inspect the server deployment logs.'


def main():
    source = Path(os.environ['DEPLOY_SOURCE'])
    state = Path(os.environ['DEPLOY_STATE'])
    compose = Path(os.environ['DEPLOY_COMPOSE'])
    url = os.environ['DEPLOY_URL'].rstrip('/')
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        check_main(source, state, compose, url)


def check_main(source, state, compose, url):
    run('git', '-C', source, 'fetch', 'origin', 'main')
    sha = output('git', '-C', source, 'rev-parse', 'FETCH_HEAD')
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise RuntimeError('Invalid release revision')
    deployed = state / 'deployed.json'
    if deployed.exists() and json.loads(deployed.read_text())['sha'] == sha:
        print('Already deployed', sha, flush=True)
        report_status(state, sha, 'success', 'Verified release is live.')
        return
    # Leave a failed commit visibly failed while retrying, rather than posting
    # pending/failure repeatedly on every timer tick.
    if read_status(state / 'status.json').get('sha') != sha:
        report_status(state, sha, 'pending', 'Building and checking the production release.')
    try:
        deploy_release(source, state, compose, url, sha)
    except Exception as error:
        report_status(state, sha, 'failure', failure_description(error))
        raise
    report_status(state, sha, 'success', 'Verified release is live.')


def deploy_release(source, state, compose, url, sha):
    deployed = state / 'deployed.json'
    image = f'rotterdam_live_web:{sha}'
    previous = output('docker', 'inspect', 'rotterdam_live_web', '--format', '{{.Image}}')
    # Retain an explicit tag even when the old running image has lost its name.
    try:
        run('docker', 'tag', previous, 'rotterdam_live_web:rollback')
    except subprocess.CalledProcessError:
        # Older maintenance may have deleted the running image's metadata.
        # Snapshot its filesystem so the first release can still roll back.
        run('docker', 'commit', 'rotterdam_live_web', 'rotterdam_live_web:rollback')
    with tempfile.TemporaryDirectory(prefix='release-', dir=state) as directory:
        release = Path(directory)
        archive = release / 'source.tar'
        with archive.open('wb') as stream:
            run('git', '-C', source, 'archive', sha, 'web', stdout=stream)
        run('tar', '-xf', archive, '-C', release)
        (release / 'web/public/version.json').write_text(json.dumps({'sha': sha}) + '\n')
        # Build and test before touching the running container.
        run('docker', 'build', '--target', 'builder', '-t', f'{image}-builder', release / 'web')
        run('docker', 'run', '--rm', f'{image}-builder', 'npm', 'test')
        # Exercise the real frontend controller against the production backend.
        run('docker', 'run', '--rm', f'{image}-builder', 'node', 'scripts/check-live-weather.mjs', url)
        run('docker', 'build', '-t', image, release / 'web')
        override = release / 'override.json'

        def activate(tag):
            override.write_text(json.dumps({'services': {'web': {'image': tag}}}))
            run('docker', 'compose', '-p', 'rotterdam-live', '--project-directory', compose.parent,
                '-f', compose, '-f', override, 'up', '-d', '--no-deps', '--no-build',
                '--wait', '--wait-timeout', '90', 'web')
            run('docker', 'exec', 'rotterdam_live_nginx', 'nginx', '-t')
            run('docker', 'exec', 'rotterdam_live_nginx', 'nginx', '-s', 'reload')

        try:
            activate(image)
            for attempt in range(15):
                try:
                    with urllib.request.urlopen(url + '/version.json?release=' + sha, timeout=15) as response:
                        actual = json.load(response)['sha']
                    if actual != sha:
                        raise RuntimeError(f'Expected {sha}, served {actual}')
                    with urllib.request.urlopen(url + '/health/ready', timeout=15) as response:
                        health = json.load(response)
                        if not health.get('database', {}).get('connected') or not health.get('redis', {}).get('connected'):
                            raise RuntimeError('Backend dependencies are not ready')
                    break
                except Exception:
                    if attempt == 14:
                        raise
                    time.sleep(2)
        except BaseException:
            print('Deployment failed; restoring previous frontend', flush=True)
            activate('rotterdam_live_web:rollback')
            raise
        pending = state / 'deployed.tmp'
        pending.write_text(json.dumps({'sha': sha, 'image': image, 'previous_image': previous}) + '\n')
        pending.replace(deployed)
        print('Deployed and verified', sha, flush=True)
    # Bound this application's retained images without pruning other services.
    # Cleanup failure must not turn a verified release into a failed deployment.
    try:
        tags = output('docker', 'image', 'ls', 'rotterdam_live_web', '--format', '{{.Tag}}').splitlines()
        older = 0
        for tag in tags:
            if re.fullmatch('[0-9a-f]{40}-builder', tag):
                run('docker', 'image', 'rm', f'rotterdam_live_web:{tag}')
            elif re.fullmatch('[0-9a-f]{40}', tag) and tag != sha:
                older += 1
                if older > 2:
                    run('docker', 'image', 'rm', f'rotterdam_live_web:{tag}')
    except subprocess.CalledProcessError as error:
        print('Release is live; image cleanup needs attention:', error, flush=True)


if __name__ == '__main__':
    main()
