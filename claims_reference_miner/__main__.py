from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from .config import ReferenceMinerConfig
from .runner import run_reference_miner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the private Claims reference miner and emit a Bronze manifest.")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--text", type=Path)
    parser.add_argument("--artifact-json", type=Path)
    parser.add_argument("--supplement", type=Path, action="append", default=[])
    parser.add_argument("--retry-reasoning-effort", choices=("none", "low", "high", "max"))
    parser.add_argument("--reasoning-effort", choices=("none", "low", "high", "max"), help="Native reasoning setting for scientific extraction")
    parser.add_argument("--output-schema", choices=("agent_v1", "scientific_result_v1.1"))
    parser.add_argument("--vision", action="store_true", help="Include PDF page images for a vision-capable scientific extraction model")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--claims-repo", type=Path, help="Path to the public Claims repo.")
    parser.add_argument("--paper-id", help="Canonical backend paper_id to use in the Bronze manifest.")
    parser.add_argument("--reference-release-id")
    parser.add_argument("--reference-profile-id")
    parser.add_argument("--runtime", choices=("dspy-react", "langchain-agent", "agent-cli", "dspy-predict"))
    parser.add_argument("--harness")
    parser.add_argument("--model")
    parser.add_argument("--pdf-reader", choices=("pdf-inspector", "pypdf", "grobid", "docling"))
    parser.add_argument("--inner-command")
    parser.add_argument("--max-agent-iters", type=int)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    inputs = [(kind, value) for kind, value in (("pdf", args.pdf), ("text", args.text), ("artifact_json", args.artifact_json)) if value]
    if len(inputs) != 1:
        parser.error("Provide exactly one of --pdf, --text, or --artifact-json.")

    root = Path(__file__).resolve().parents[1]
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(root / ".env")
    if args.claims_repo:
        load_dotenv(args.claims_repo / ".env")
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    config = ReferenceMinerConfig.from_env(base_dir=root)
    if args.output_schema:
        config.output_schema = args.output_schema
    if args.retry_reasoning_effort is not None:
        config.scientific_retry_reasoning_effort = args.retry_reasoning_effort
    if args.reasoning_effort is not None:
        config.scientific_reasoning_effort = args.reasoning_effort
    if args.vision:
        config.scientific_vision = True
    if config.output_schema == "scientific_result_v1.1":
        config.runtime = "dspy-predict"
        config.pdf_reader = "docling"
        if not args.model:
            config.model = "deepseek/deepseek-v4-flash-0731"
    if args.claims_repo:
        config.claims_repo = args.claims_repo
    if args.paper_id:
        config.paper_id = args.paper_id
    if args.reference_release_id:
        config.reference_release_id = args.reference_release_id
    if args.reference_profile_id:
        config.reference_profile_id = args.reference_profile_id
    if args.runtime:
        config.runtime = args.runtime
    if args.harness:
        config.harness = args.harness
    if args.model:
        config.model = args.model
    if args.pdf_reader:
        config.pdf_reader = args.pdf_reader
    if args.inner_command:
        config.inner_command = args.inner_command
    if args.max_agent_iters:
        config.max_agent_iters = args.max_agent_iters

    input_kind, input_path = inputs[0]
    manifest = run_reference_miner(
        input_path=input_path,
        input_kind=input_kind,  # type: ignore[arg-type]
        output_dir=args.output_dir,
        config=config,
        supplements=args.supplement,
    )
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
