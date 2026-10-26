import json
import subprocess
from pathlib import Path

import pytest

from claims_reference_miner.config import ReferenceMinerConfig
from claims_reference_miner.release_lock import LOCK_FIELDS, verify_release_lock


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
    payload = {
        "schema_version": "claims_reference_release_v1",
        "claims_commit": _git(repo, "rev-parse", "HEAD"),
        **{field: getattr(config, field) for field in LOCK_FIELDS},
    }
    lock_path.write_text(json.dumps(payload))
    assert len(verify_release_lock(config)) == 64
    with pytest.raises(ValueError, match="runtime"):
        verify_release_lock(config.model_copy(update={"model": "different"}))
    (repo / "miner" / "agent_v1" / "runner.py").write_text("version = 2\n")
    with pytest.raises(ValueError, match="checkout"):
        verify_release_lock(config)
