"""Exercise deployment ordering and failure boundaries without production Docker."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
SHA = "a" * 40


@pytest.fixture
def release_env(tmp_path):
    root = tmp_path / "production"
    shared = root / "shared"
    (shared / "secrets").mkdir(parents=True)
    (shared / ".env.prod").touch()
    (shared / "secrets/web.htpasswd").write_text("test")
    release = root / "releases" / SHA
    (release / "deploy").mkdir(parents=True)
    shutil.copy(DEPLOY / "release.sh", release / "deploy/release.sh")
    old = root / "old"
    old.mkdir()
    (root / "current").symlink_to(old)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text("""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['DOCKER_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
mode = os.environ.get('FAIL_MODE')
if mode == 'build' and 'build' in args:
    sys.exit(1)
if mode == 'migration' and 'run' in args:
    sys.exit(1)
if mode == 'forecasts' and 'cs2eye.deployment.prepare' in args:
    sys.exit(1)
if mode == 'reports' and 'cs2eye.deployment.ai_reports' in args:
    sys.exit(1)
if mode == 'api-data' and 'cs2eye.deployment.verify_results' in args:
    sys.exit(1)
if any('pg_dump' in arg for arg in args) and mode != 'empty-backup':
    sys.stdout.write('database-backup')
if 'pg_restore' in args:
    sys.exit(0 if sys.stdin.read() == 'database-backup' else 1)
""")
    docker.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/sh\nprintf 401\n")
    curl.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
               CS2EYE_DEPLOY_ROOT=str(root), CS2EYE_IMAGE_PREFIX="cs2eye",
               CS2EYE_RELEASE=SHA, CS2EYE_BUILD_LOCAL="true",
               DOCKER_LOG=str(tmp_path / "docker.log"))
    return root, release, env


@pytest.mark.parametrize("mode", ["build", "empty-backup"])
def test_preflight_failure_keeps_production_running(release_env, mode):
    root, release, env = release_env
    env["FAIL_MODE"] = mode
    result = subprocess.run(["bash", str(release / "deploy/release.sh")], env=env, capture_output=True)
    assert result.returncode != 0
    calls = [json.loads(line) for line in Path(env["DOCKER_LOG"]).read_text().splitlines()]
    assert not any("stop" in call or "up" in call for call in calls)
    assert (root / "current").resolve() == root / "old"


def test_failed_migration_does_not_mark_release_successful(release_env):
    root, release, env = release_env
    env["FAIL_MODE"] = "migration"
    result = subprocess.run(["bash", str(release / "deploy/release.sh")], env=env, capture_output=True)
    assert result.returncode != 0
    assert (root / "current").resolve() == root / "old"
    assert list((root / "backups").glob("*.dump"))


def test_missing_forecasts_prevent_successful_release(release_env):
    root, release, env = release_env
    env["FAIL_MODE"] = "forecasts"
    result = subprocess.run(["bash", str(release / "deploy/release.sh")], env=env, capture_output=True)
    assert result.returncode != 0
    assert (root / "current").resolve() == root / "old"
    calls = [json.loads(line) for line in Path(env["DOCKER_LOG"]).read_text().splitlines()]
    assert not any("up" in call for call in calls)
    assert any("start" in call and "api" in call and "bot" in call for call in calls)


def test_failed_ai_report_import_prevents_successful_release(release_env):
    root, release, env = release_env
    env["FAIL_MODE"] = "reports"
    result = subprocess.run(["bash", str(release / "deploy/release.sh")], env=env, capture_output=True)
    assert result.returncode != 0
    assert (root / "current").resolve() == root / "old"
    calls = [json.loads(line) for line in Path(env["DOCKER_LOG"]).read_text().splitlines()]
    assert not any("up" in call for call in calls)


def test_success_preserves_database_container_and_previous_release(release_env):
    root, release, env = release_env
    subprocess.run(["bash", str(release / "deploy/release.sh")], env=env, check=True, capture_output=True)
    assert (root / "current").resolve() == release
    assert (root / "previous").resolve() == root / "old"
    calls = [json.loads(line) for line in Path(env["DOCKER_LOG"]).read_text().splitlines()]
    prepare = next(i for i, call in enumerate(calls) if "cs2eye.deployment.prepare" in call)
    assert prepare < next(i for i, call in enumerate(calls) if "up" in call)
    up = next(call for call in calls if "up" in call)
    assert "db" not in up
    assert "--no-deps" in up
    backup = next((root / "backups").glob("*.dump"))
    assert backup.stat().st_mode & 0o777 == 0o600


def test_update_deploys_only_committed_production_history(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()

    git("init", "-b", "production")
    git("config", "user.name", "Deployment test")
    git("config", "user.email", "test@example.invalid")
    (source / "deploy").mkdir()
    (source / "deploy/release.sh").write_text('printf "%s" "$CS2EYE_RELEASE" > "$CS2EYE_DEPLOY_ROOT/deployed"\n')
    git("add", ".")
    git("commit", "-m", "production")
    sha = git("rev-parse", "HEAD")
    # An uncommitted edit must never enter the extracted release.
    (source / "deploy/release.sh").write_text("exit 42\n")
    root = tmp_path / "server"
    (root / "shared").mkdir(parents=True)
    (root / "shared/deploy.conf").write_text(f"CS2EYE_GIT_URL='{source}'\nCS2EYE_GIT_BRANCH=production\n")
    env = dict(os.environ, CS2EYE_DEPLOY_ROOT=str(root))
    subprocess.run(["bash", str(DEPLOY / "update.sh")], env=env, check=True, capture_output=True)
    assert (root / "deployed").read_text() == sha
    git("checkout", "-b", "other")
    git("add", ".")
    git("commit", "-m", "not production")
    other = git("rev-parse", "HEAD")
    result = subprocess.run(["bash", str(DEPLOY / "update.sh"), other], env=env, capture_output=True)
    assert result.returncode != 0
    assert (root / "deployed").read_text() == sha


def test_api_data_verification_prevents_false_release_success(release_env):
    root, release, env = release_env
    env["FAIL_MODE"] = "api-data"
    result = subprocess.run(["bash", str(release / "deploy/release.sh")], env=env, capture_output=True)
    assert result.returncode != 0
    assert (root / "current").resolve() == root / "old"
    calls = [json.loads(line) for line in Path(env["DOCKER_LOG"]).read_text().splitlines()]
    verify = next(i for i, call in enumerate(calls) if "cs2eye.deployment.verify_results" in call)
    assert verify > next(i for i, call in enumerate(calls) if "up" in call)
