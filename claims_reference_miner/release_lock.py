"""Fail closed if a Bronze/reference run differs from its published release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .config import ReferenceMinerConfig

LOCK_FIELDS = (
    "reference_release_id", "reference_profile_id", "runtime", "harness",
    "model", "pdf_reader", "api_base", "temperature", "max_tokens", "max_agent_iters",
    "max_repair_attempts", "cli_command", "inner_command",
)


def reference_miner_source_sha256(root: Path | None = None) -> str:
    """Hash the installed reference runner and build definition by relative path."""
    root = root or Path(__file__).resolve().parents[1]
    sources = sorted((root / "claims_reference_miner").rglob("*.py"))
    paths = [*sources, root / "pyproject.toml"]
    if not sources or any(not path.is_file() for path in paths):
        raise ValueError("reference miner source is incomplete")
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def build_release_lock(config: ReferenceMinerConfig) -> dict:
    """Make a candidate lock from a clean, committed Claims extraction checkout."""
    repo = config.claims_repo.resolve()
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        changed = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain", "--",
             "miner/agent_v1", "validator/agent_v1"], text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("reference Claims checkout is not a readable Git release") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or changed:
        raise ValueError("reference Claims checkout is not a clean committed release")
    return {
        "schema_version": "claims_reference_release_v1",
        "claims_commit": commit,
        "reference_miner_source_sha256": reference_miner_source_sha256(),
        **{field: getattr(config, field) for field in LOCK_FIELDS},
    }


def verify_release_lock(config: ReferenceMinerConfig) -> str | None:
    """Return the lock digest, or None only for explicit development runs."""
    if config.release_lock_path is None:
        return None
    try:
        lock = json.loads(config.release_lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("reference release lock is missing or invalid") from exc
    if not isinstance(lock, dict) or lock.get("schema_version") != "claims_reference_release_v1":
        raise ValueError("reference release lock has the wrong schema")
    commit = lock.get("claims_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("reference release lock needs a full Claims commit")
    if lock.get("reference_miner_source_sha256") != reference_miner_source_sha256():
        raise ValueError("reference miner source differs from release lock")
    expected = {field: getattr(config, field) for field in LOCK_FIELDS}
    if any(lock.get(field) != value for field, value in expected.items()):
        raise ValueError("reference runtime differs from release lock")
    if build_release_lock(config)["claims_commit"] != commit:
        raise ValueError("reference Claims checkout differs from locked release")
    canonical = json.dumps(lock, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a candidate Bronze reference release lock")
    parser.add_argument("--claims-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = ReferenceMinerConfig.from_env()
    config.claims_repo = args.claims_repo
    lock = build_release_lock(config)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(lock, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
