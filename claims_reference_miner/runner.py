from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Literal

from .config import ReferenceMinerConfig
from .manifest import BronzeManifest, sha256_file, stable_json_hash


InputKind = Literal["pdf", "text", "artifact_json"]


def run_reference_miner(
    *,
    input_path: Path,
    input_kind: InputKind,
    output_dir: Path | None = None,
    config: ReferenceMinerConfig | None = None,
) -> BronzeManifest:
    config = config or ReferenceMinerConfig.from_env(base_dir=Path(__file__).resolve().parents[1])
    claims_repo = config.claims_repo.resolve()
    _ensure_claims_importable(claims_repo)

    from miner.agent_v1.config import AgentV1Config
    from miner.agent_v1.runner import AgentV1Runner

    input_path = input_path.resolve()
    run_dir = (output_dir or (config.output_dir / input_path.stem)).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    agent_config = AgentV1Config.from_env(claims_repo)
    agent_config.output_dir = config.output_dir
    agent_config.runtime = config.runtime
    agent_config.model = config.model
    agent_config.pdf_reader = config.pdf_reader
    agent_config.api_key = config.api_key
    agent_config.api_base = config.api_base
    agent_config.temperature = config.temperature
    agent_config.max_tokens = config.max_tokens
    agent_config.max_agent_iters = config.max_agent_iters
    agent_config.max_repair_attempts = config.max_repair_attempts
    agent_config.cli_command = config.cli_command
    if config.inner_command:
        os.environ["CLAIMS_AGENT_INNER_COMMAND"] = config.inner_command

    runner = AgentV1Runner(agent_config)
    paper_override = {"paper_id": config.paper_id} if config.paper_id else None
    if input_kind == "pdf":
        artifact = runner.run_from_pdf(input_path, output_dir=run_dir, paper_override=paper_override)
    elif input_kind == "text":
        artifact = runner.run_from_text(input_path, output_dir=run_dir)
    else:
        artifact = runner.run_from_artifact_json(input_path, output_dir=run_dir)

    if config.paper_id:
        artifact.paper.paper_id = config.paper_id
        artifact_path = run_dir / "agent_output.json"
        artifact_path.write_text(
            json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    artifact_path = run_dir / "agent_output.json"
    source_payload_path = run_dir / "source_payload.json"
    if not source_payload_path.exists():
        source_payload_path = run_dir / "data" / "agent_v1_source_payload.json"
    artifact_sha256 = sha256_file(artifact_path)
    if artifact_sha256 is None:
        raise RuntimeError(f"Reference miner did not write expected artifact: {artifact_path}")

    paper_id = artifact.paper.paper_id
    runtime_metrics = artifact.metadata.get("runtime_metrics") if isinstance(artifact.metadata.get("runtime_metrics"), dict) else {}
    models = [item for item in runtime_metrics.get("models", []) if isinstance(item, str) and item]
    model = (
        _model_from_command(config.inner_command)
        or str(artifact.metadata.get("model") or runtime_metrics.get("model") or "")
        or (models[0] if len(models) == 1 else "")
        or config.model
    )
    harness = (
        config.harness
        or str(artifact.metadata.get("harness") or runtime_metrics.get("harness") or "")
        or _harness_from_command(config.inner_command)
        or _harness_from_command(config.cli_command)
        or (config.runtime if config.runtime != "agent-cli" else "agent-cli")
    )
    manifest_payload = {
        "paper_id": paper_id,
        "reference_release_id": config.reference_release_id,
        "reference_profile_id": config.reference_profile_id,
        "artifact_sha256": artifact_sha256,
    }
    bronze_record_id = "bronze_" + stable_json_hash(manifest_payload)[:16]
    manifest = BronzeManifest(
        bronze_record_id=bronze_record_id,
        paper_id=paper_id,
        reference_release_id=config.reference_release_id,
        reference_profile_id=config.reference_profile_id,
        model_runtime_id=model or harness,
        pipeline_version="claims-reference-miner/0.1.0",
        source_sha256=sha256_file(input_path),
        artifact_sha256=artifact_sha256,
        source_payload_sha256=sha256_file(source_payload_path),
        artifact_path=str(artifact_path),
        source_payload_path=str(source_payload_path) if source_payload_path.exists() else None,
        metadata={
            "input_kind": input_kind,
            "input_path": str(input_path),
            "runtime": config.runtime,
            "harness": harness,
            "model": model,
            "models": models or ([model] if model else []),
            "pdf_reader": config.pdf_reader,
            "claims_repo": str(claims_repo),
        },
    )
    (run_dir / "bronze_manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def _ensure_claims_importable(claims_repo: Path) -> None:
    if not claims_repo.exists():
        raise RuntimeError(f"Claims repo does not exist: {claims_repo}")
    repo_text = str(claims_repo)
    if repo_text not in sys.path:
        sys.path.insert(0, repo_text)
    existing = os.environ.get("PYTHONPATH", "")
    paths = [repo_text, *([existing] if existing else [])]
    os.environ["PYTHONPATH"] = os.pathsep.join(paths)


def _model_from_command(command: str | list[str]) -> str:
    parts = _command_parts(command)
    for index, part in enumerate(parts):
        if part in {"-m", "--model"} and index + 1 < len(parts):
            if _is_python_module_flag(parts, index):
                continue
            return _model_id_or_empty(parts[index + 1])
        if part.startswith("--model="):
            return _model_id_or_empty(part.split("=", 1)[1])
    return ""


def _harness_from_command(command: str | list[str]) -> str:
    parts = _command_parts(command)
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


def _command_parts(command: str | list[str]) -> list[str]:
    if isinstance(command, list):
        return [str(part) for part in command if str(part)]
    if command.strip():
        try:
            return shlex.split(command)
        except ValueError:
            return command.split()
    return []


def _is_python_module_flag(command: list[str], index: int) -> bool:
    if command[index] != "-m" or index == 0:
        return False
    executable = Path(command[index - 1]).name
    if executable.startswith("python"):
        return True
    return index == 1 and Path(command[0]).name.startswith("python")


def _model_id_or_empty(value: str | None) -> str:
    model = str(value or "").strip()
    if not model:
        return ""
    if model.lower() in {"agent-cli", "claude-cli", "codex-cli", "hermes-cli", "hermes-agent", "dspy-react", "langchain-agent"}:
        return ""
    if model.startswith(("miner.", "neurons.", "claims_reference_miner")) or ".wrappers." in model:
        return ""
    return model
