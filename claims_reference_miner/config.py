from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ReferenceMinerConfig(BaseModel):
    claims_repo: Path
    output_dir: Path
    output_schema: Literal["agent_v1", "scientific_result_v1.1"] = "agent_v1"
    scientific_vision: bool = False
    scientific_request_deadline: float = Field(default=600, gt=0)
    scientific_reasoning_effort: Literal["none", "low", "high", "max"] = "none"
    scientific_retry_reasoning_effort: Literal["none", "low", "high", "max"] = "low"
    release_lock_path: Path | None = None
    paper_id: str = ""
    reference_release_id: str = "reference-v0"
    reference_profile_id: str = "reference-agent-v1-strong"
    runtime: str = "dspy-react"
    harness: str = ""
    model: str = "deepseek/deepseek-v4-flash-0731"
    pdf_reader: str = "pdf-inspector"
    api_key: str | None = None
    api_base: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.0
    max_tokens: int = 32768
    max_agent_iters: int = 6
    max_repair_attempts: int = 3
    cli_command: list[str] = []
    inner_command: str = ""

    @classmethod
    def from_env(cls, *, base_dir: Path | None = None) -> ReferenceMinerConfig:
        root = base_dir or Path.cwd()
        default_claims_repo = _default_claims_repo(root)
        output_schema = os.getenv("CLAIMS_REFERENCE_MINER_OUTPUT_SCHEMA", "agent_v1")
        scientific = output_schema == "scientific_result_v1.1"
        runtime = os.getenv("CLAIMS_REFERENCE_MINER_RUNTIME", "dspy-predict" if scientific else os.getenv("SUBNET_CLAIMS_AGENT_RUNTIME", "dspy-react"))
        model_env = (os.getenv("CLAIMS_SCIENTIFIC_RESULT_MODEL", "deepseek/deepseek-v4-flash-0731")
                     if scientific else os.getenv("CLAIMS_REFERENCE_MINER_MODEL"))
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
            output_schema=output_schema,
            scientific_request_deadline=float(os.getenv("CLAIMS_SCIENTIFIC_RESULT_REQUEST_DEADLINE", "600")),
            scientific_retry_reasoning_effort=os.getenv("CLAIMS_SCIENTIFIC_RESULT_RETRY_REASONING_EFFORT", "low"),
            scientific_reasoning_effort=os.getenv("CLAIMS_SCIENTIFIC_RESULT_REASONING_EFFORT", "none"),
            scientific_vision=os.getenv("CLAIMS_SCIENTIFIC_RESULT_VISION", "").strip().lower() in {"1", "true", "yes"},
            claims_repo=Path(os.getenv("CLAIMS_REFERENCE_MINER_CLAIMS_REPO", str(default_claims_repo))).expanduser(),
            output_dir=Path(os.getenv("CLAIMS_REFERENCE_MINER_OUTPUT_DIR", str(root / "outputs"))).expanduser(),
            release_lock_path=(Path(os.environ["CLAIMS_REFERENCE_RELEASE_LOCK"]).expanduser()
                               if os.getenv("CLAIMS_REFERENCE_RELEASE_LOCK") else None),
            paper_id=os.getenv("CLAIMS_REFERENCE_MINER_PAPER_ID", ""),
            reference_release_id=os.getenv("CLAIMS_REFERENCE_RELEASE_ID", "reference-v0"),
            reference_profile_id=os.getenv("CLAIMS_REFERENCE_PROFILE_ID", "reference-agent-v1-strong"),
            runtime=runtime,
            harness=harness,
            model=_reference_model(model_env),
            pdf_reader=(
                os.getenv("CLAIMS_REFERENCE_MINER_PDF_READER")
                or os.getenv("SUBNET_CLAIMS_PDF_READER")
                or os.getenv("SUBNET_CLAIMS_PDF_EXTRACTION_METHOD")
                or ("docling" if scientific else "pdf-inspector")
            ),
            api_key=os.getenv("CLAIMS_INFERENCE_TOKEN") or os.getenv("OPENROUTER_API_KEY"),
            api_base=os.getenv("CLAIMS_INFERENCE_BASE_URL") or os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
            temperature=float(os.getenv("CLAIMS_REFERENCE_MINER_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("CLAIMS_REFERENCE_MINER_MAX_TOKENS", "32768")),
            max_agent_iters=int(os.getenv("CLAIMS_REFERENCE_MINER_MAX_ITERS", "6")),
            max_repair_attempts=int(os.getenv("CLAIMS_REFERENCE_MINER_MAX_REPAIR_ATTEMPTS", "3")),
            cli_command=cli_command,
            inner_command=inner_command,
        )


def _default_claims_repo(base_dir: Path) -> Path:
    cwd = Path.cwd().resolve()
    sibling = base_dir.resolve().parent / "Claims"
    for candidate in (cwd, sibling):
        if (candidate / "miner" / "agent_v1").is_dir() and (
            candidate / "validator" / "agent_v1"
        ).is_dir():
            return candidate
    return sibling


def _reference_model(model_env: str | None) -> str:
    if model_env and not _is_harness_id(model_env):
        return model_env
    if model_env and _is_harness_id(model_env):
        return os.getenv("SUBNET_CLAIMS_REFERENCE_MODEL", "")
    return os.getenv("SUBNET_CLAIMS_REFERENCE_MODEL", os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731"))


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
