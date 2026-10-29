"""Run the frozen reference extraction package on one competition paper."""

from __future__ import annotations

import argparse
import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def run(request_path: Path, output_path: Path) -> None:
    import miner.agent_v1 as agent_package
    from miner.agent_v1.artifact_validator import validate_agent_artifact
    from miner.agent_v1.config import AgentV1Config
    from miner.agent_v1.runner import AgentV1Runner

    request = _object(request_path)
    profile = json.loads(files("claims_reference_miner").joinpath("competition_profile.json").read_text(encoding="utf-8"))
    if request.get("schema_version") != "claims_competition_request_v1":
        raise ValueError("unsupported competition request schema")
    paper = request.get("paper")
    inference = request.get("inference")
    if not isinstance(paper, dict) or not isinstance(inference, dict):
        raise ValueError("competition request needs paper and inference objects")
    paper_id = paper.get("paper_id")
    if not isinstance(paper_id, str) or not paper_id:
        raise ValueError("competition paper_id is missing")
    if (inference.get("model") != profile["model"]
        or profile["model"] not in inference.get("allowed_models", [])):
        raise ValueError("reference model differs from the sealed worker request")
    max_output_tokens = inference.get("max_output_tokens")
    if (type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 32768):
        raise ValueError("worker max_output_tokens is invalid")
    api_base = os.environ.get("CLAIMS_INFERENCE_BASE_URL", "").strip()
    api_key = os.environ.get("CLAIMS_INFERENCE_TOKEN", "").strip()
    if not api_base.startswith(("http://", "https://")) or not api_key:
        raise ValueError("paper-scoped inference gateway credentials are required")
    pdf_path = Path(request.get("pdf_path", ""))
    if not pdf_path.is_absolute():
        pdf_path = request_path.parent / pdf_path
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ValueError("competition PDF is missing")

    config = AgentV1Config.from_env()
    config.runtime = profile["runtime"]
    # DSPy/LiteLLM consumes the first provider prefix. Bifrost must receive
    # openrouter/<catalog-model> so it routes to the configured OpenRouter key.
    config.model = "openrouter/openrouter/" + profile["model"]
    config.pdf_reader = profile["pdf_reader"]
    config.provider = "openrouter"
    config.api_base = api_base
    config.api_key = api_key
    config.temperature = profile["temperature"]
    config.max_tokens = min(profile["max_tokens"], max_output_tokens)
    config.max_agent_iters = profile["max_agent_iters"]
    config.max_repair_attempts = profile["max_repair_attempts"]
    config.skill_dir = Path(agent_package.__file__).parent / "skills" / "compiler"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = AgentV1Runner(config).run_from_pdf(
        pdf_path, output_dir=output_path.parent / "reference-run",
        paper_override={
            "paper_id": paper_id,
            "title": str(paper.get("title") or paper_id),
            "source_url": str(paper.get("source_url") or ""),
            "source_sha256": str(paper.get("source_sha256") or ""),
        },
    )
    artifact.metadata["reference_release_id"] = profile["reference_release_id"]
    artifact.metadata["reference_profile_id"] = profile["reference_profile_id"]
    artifact.metadata["reference_model"] = profile["model"]
    issues = validate_agent_artifact(artifact)
    if issues:
        raise ValueError(f"reference artifact failed validation: {len(issues)} issue(s)")
    if artifact.paper.paper_id != paper_id:
        raise ValueError("reference artifact paper_id differs from request")
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.output)


if __name__ == "__main__":
    main()
