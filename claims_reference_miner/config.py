from __future__ import annotations

import os
import shlex
from pathlib import Path

from pydantic import BaseModel


class ReferenceMinerConfig(BaseModel):
    claims_repo: Path
    output_dir: Path
    paper_id: str = ""
    reference_release_id: str = "reference-v0"
    reference_profile_id: str = "reference-agent-v1-strong"
    runtime: str = "dspy-react"
    harness: str = ""
    model: str = "openrouter/openai/gpt-5"
    api_key: str | None = None
    api_base: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.0
    max_tokens: int = 32768
    max_agent_iters: int = 6
    max_repair_attempts: int = 3
    cli_command: list[str] = []
    inner_command: str = ""

    @classmethod
    def from_env(cls, *, base_dir: Path | None = None) -> "ReferenceMinerConfig":
        root = base_dir or Path.cwd()
        default_claims_repo = root.parent / "Claims"
        runtime = os.getenv("CLAIMS_REFERENCE_MINER_RUNTIME", os.getenv("SUBNET_CLAIMS_AGENT_RUNTIME", "dspy-react"))
        model_env = os.getenv("CLAIMS_REFERENCE_MINER_MODEL")
        inner_command = os.getenv("CLAIMS_REFERENCE_MINER_INNER_COMMAND", os.getenv("CLAIMS_AGENT_INNER_COMMAND", ""))
        cli_command = shlex.split(os.getenv("CLAIMS_REFERENCE_MINER_CLI_COMMAND", ""))
        harness = (
            os.getenv("CLAIMS_REFERENCE_MINER_HARNESS", "")
            or _harness_from_legacy_model(model_env)
            or _harness_from_command(inner_command)
            or _harness_from_command(cli_command)
            or (runtime if runtime != "agent-cli" else "")
        )
        return cls(
            claims_repo=Path(os.getenv("CLAIMS_REFERENCE_MINER_CLAIMS_REPO", str(default_claims_repo))).expanduser(),
            output_dir=Path(os.getenv("CLAIMS_REFERENCE_MINER_OUTPUT_DIR", str(root / "outputs"))).expanduser(),
            paper_id=os.getenv("CLAIMS_REFERENCE_MINER_PAPER_ID", ""),
            reference_release_id=os.getenv("CLAIMS_REFERENCE_RELEASE_ID", "reference-v0"),
            reference_profile_id=os.getenv("CLAIMS_REFERENCE_PROFILE_ID", "reference-agent-v1-strong"),
            runtime=runtime,
            harness=harness,
            model=_reference_model(model_env),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            api_base=os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
            temperature=float(os.getenv("CLAIMS_REFERENCE_MINER_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("CLAIMS_REFERENCE_MINER_MAX_TOKENS", "32768")),
            max_agent_iters=int(os.getenv("CLAIMS_REFERENCE_MINER_MAX_ITERS", "6")),
            max_repair_attempts=int(os.getenv("CLAIMS_REFERENCE_MINER_MAX_REPAIR_ATTEMPTS", "3")),
            cli_command=cli_command,
            inner_command=inner_command,
        )


def _reference_model(model_env: str | None) -> str:
    if model_env and not _is_harness_id(model_env):
        return model_env
    if model_env and _is_harness_id(model_env):
        return os.getenv("SUBNET_CLAIMS_REFERENCE_MODEL", "")
    return os.getenv("SUBNET_CLAIMS_REFERENCE_MODEL", os.getenv("OPENROUTER_MODEL", "openrouter/openai/gpt-5"))


def _harness_from_legacy_model(value: str | None) -> str:
    return str(value or "").strip() if _is_harness_id(value) else ""


def _harness_from_command(command: str | list[str]) -> str:
    parts = command if isinstance(command, list) else shlex.split(command) if command.strip() else []
    if not parts:
        return ""
    lowered = [Path(part).name.lower() for part in parts]
    joined = " ".join(str(part).lower() for part in parts)
    if any(part in {"hermes", "hermes-agent"} for part in lowered) or "hermes_prompt" in joined:
        return "hermes-cli"
    if any(part in {"codex", "codex-cli"} for part in lowered) or "codex_prompt" in joined:
        return "codex-cli"
    if any(part in {"claude", "claude-code", "claude-cli"} for part in lowered):
        return "claude-cli"
    if "langchain" in joined:
        return "langchain-agent"
    if "dspy" in joined:
        return "dspy-react"
    return ""


def _is_harness_id(value: str | None) -> bool:
    return str(value or "").strip().lower() in {
        "agent-cli",
        "claude-cli",
        "codex-cli",
        "hermes-cli",
        "hermes-agent",
        "dspy-react",
        "langchain-agent",
    }
