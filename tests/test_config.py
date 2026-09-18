from __future__ import annotations

from pathlib import Path

from claims_reference_miner.config import ReferenceMinerConfig


def test_installed_package_prefers_claims_checkout_working_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    claims_repo = tmp_path / "Claims"
    (claims_repo / "miner" / "agent_v1").mkdir(parents=True)
    (claims_repo / "validator" / "agent_v1").mkdir(parents=True)
    installed_package = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
    installed_package.mkdir(parents=True)
    monkeypatch.chdir(claims_repo)
    monkeypatch.delenv("CLAIMS_REFERENCE_MINER_CLAIMS_REPO", raising=False)

    config = ReferenceMinerConfig.from_env(base_dir=installed_package)

    assert config.claims_repo == claims_repo
