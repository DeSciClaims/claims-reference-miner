"""Fail closed if a Bronze/reference run differs from its published release."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess

from .config import ReferenceMinerConfig

LOCK_FIELDS = (
    "reference_release_id", "reference_profile_id", "runtime", "harness",
    "model", "pdf_reader", "api_base", "temperature", "max_tokens", "max_agent_iters",
    "max_repair_attempts", "cli_command", "inner_command",
)


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
    expected = {field: getattr(config, field) for field in LOCK_FIELDS}
    if any(lock.get(field) != value for field, value in expected.items()):
        raise ValueError("reference runtime differs from release lock")
    repo = config.claims_repo.resolve()
    try:
        actual = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL,
        ).strip()
        changed = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain", "--",
             "miner/agent_v1", "validator/agent_v1"], text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("reference Claims checkout is not a readable Git release") from exc
    if actual != commit or changed:
        raise ValueError("reference Claims checkout differs from locked release")
    canonical = json.dumps(lock, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
