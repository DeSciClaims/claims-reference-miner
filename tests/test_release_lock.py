import json
import subprocess
from pathlib import Path

import pytest

from claims_reference_miner.config import ReferenceMinerConfig
from claims_reference_miner import release_lock
from claims_reference_miner.release_lock import (
    build_release_lock, reference_miner_source_sha256, verify_release_lock,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def test_reference_lock_binds_claims_commit_and_runtime(tmp_path: Path):
    repo = tmp_path / "Claims"
    (repo / "miner" / "agent_v1").mkdir(parents=True)
    (repo / "validator" / "agent_v1").mkdir(parents=True)
    (repo / "miner" / "agent_v1" / "runner.py").write_text("version = 1\n")
    (repo / "validator" / "agent_v1" / "scorer.py").write_text("version = 1\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.org")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "reference")
    lock_path = tmp_path / "release.json"
    config = ReferenceMinerConfig(claims_repo=repo, output_dir=tmp_path / "outputs", release_lock_path=lock_path)
    payload = build_release_lock(config)
    assert payload["claims_commit"] == _git(repo, "rev-parse", "HEAD")
    assert len(payload["reference_miner_source_sha256"]) == 64
    lock_path.write_text(json.dumps(payload))
    assert len(verify_release_lock(config)) == 64
    with pytest.raises(ValueError, match="runtime"):
        verify_release_lock(config.model_copy(update={"model": "different"}))
    (repo / "miner" / "agent_v1" / "runner.py").write_text("version = 2\n")
    with pytest.raises(ValueError, match="checkout"):
        verify_release_lock(config)


def test_reference_lock_rejects_changed_runner_source(tmp_path: Path, monkeypatch):
    repo = tmp_path / "Claims"
    (repo / "miner" / "agent_v1").mkdir(parents=True)
    (repo / "validator" / "agent_v1").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.org")
    _git(repo, "config", "user.name", "Test")
    (repo / "miner" / "agent_v1" / "runner.py").write_text("version = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "reference")
    path = tmp_path / "release.json"
    config = ReferenceMinerConfig(claims_repo=repo, output_dir=tmp_path, release_lock_path=path)
    path.write_text(json.dumps(build_release_lock(config)))
    monkeypatch.setattr(release_lock, "reference_miner_source_sha256", lambda: "0" * 64)
    with pytest.raises(ValueError, match="reference miner source"):
        verify_release_lock(config)


def test_reference_source_digest_changes_with_source_and_build_definition(tmp_path: Path):
    package = tmp_path / "claims_reference_miner"
    package.mkdir()
    runner = package / "runner.py"
    runner.write_text("version = 1\n")
    build = tmp_path / "pyproject.toml"
    build.write_text("[project]\nname = 'reference'\n")
    first = reference_miner_source_sha256(tmp_path)
    runner.write_text("version = 2\n")
    second = reference_miner_source_sha256(tmp_path)
    assert first != second
    build.write_text("[project]\nname = 'reference-new'\n")
    assert second != reference_miner_source_sha256(tmp_path)
