"""Reference runner for v1.1 JSON/CSV packages; old competition workers stay agent_v1."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .config import ReferenceMinerConfig
from .manifest import BronzeManifest, sha256_file, stable_json_hash


def run_scientific_reference(*, input_path: Path, input_kind: str, output_dir: Path | None,
                             config: ReferenceMinerConfig, supplements: list[Path],
                             release_lock_sha256: str | None) -> BronzeManifest:
    from miner.scientific_result_v1.pipeline import extract_pdf
    from miner.scientific_result_v1.runtime import DspyRuntime

    if input_kind != "pdf" or config.pdf_reader != "docling" or config.runtime != "dspy-predict":
        raise ValueError("scientific_result_v1.1 requires PDF input, docling reader, and dspy-predict runtime")
    if not config.api_key or not config.paper_id:
        raise ValueError("scientific_result_v1.1 needs API credentials and an assigned paper_id")
    if config.inner_command or config.cli_command:
        raise ValueError("scientific_result_v1.1 does not support CLI runtime commands")
    run_dir = (output_dir or config.output_dir / input_path.stem).resolve()
    # As in the competition adapter, scoped reference gateways need the explicit
    # OpenRouter provider route; the public OpenRouter API wants the catalog ID.
    model_route = (None if urlparse(config.api_base).hostname == "openrouter.ai"
                   else "openrouter/" + config.model.removeprefix("openrouter/"))
    runtime = DspyRuntime(model=config.model, api_key=config.api_key, api_base=config.api_base,
                          model_route=model_route,
                          temperature=config.temperature, max_tokens=config.max_tokens,
                          reasoning_effort=config.scientific_reasoning_effort,
                          retry_reasoning_effort=config.scientific_retry_reasoning_effort,
                          request_deadline=config.scientific_request_deadline)
    payload = extract_pdf(input_path.resolve(), run_dir, runtime=runtime, paper_id=config.paper_id,
                          supplements=supplements, max_attempts=config.max_repair_attempts,
                          vision=config.scientific_vision)
    report = validate_reference(payload=payload, run_dir=run_dir, input_path=input_path,
                                config=config, model_route=model_route)
    if not report["submission_ready"]:
        raise ValueError("Reference extraction is not submission-ready; inspect reference-validation/validation_report.json")
    artifact = run_dir / "extraction.json"
    files = [artifact, *(run_dir / table["csv_file"] for table in payload["tables"])]
    package_hashes = {path.name: sha256_file(path) for path in files}
    package_hash = stable_json_hash(package_hashes)
    manifest = BronzeManifest(
        bronze_record_id="bronze_" + stable_json_hash({
            "paper_id": config.paper_id, "reference_release_id": config.reference_release_id,
            "reference_profile_id": config.reference_profile_id, "package_sha256": package_hash,
        })[:16],
        paper_id=config.paper_id, reference_release_id=config.reference_release_id,
        reference_profile_id=config.reference_profile_id, model_runtime_id=config.model,
        pipeline_version="claims-scientific-result/1.1",
        source_sha256=sha256_file(input_path), artifact_sha256=sha256_file(artifact),
        source_payload_sha256=sha256_file(run_dir / "source_payload.json"),
        artifact_path=str(artifact), source_payload_path=str(run_dir / "source_payload.json"),
        metadata={"output_schema": "scientific_result_v1.1", "runtime": "dspy-predict",
                  "pdf_reader": "docling", "model": config.model,
                  "api_model": model_route or config.model.removeprefix("openrouter/"),
                  "reference_lock_sha256": release_lock_sha256,
                  "package_sha256": package_hash, "package_files": package_hashes,
                  "validation_report_sha256": sha256_file(run_dir / "reference-validation" / "validation_report.json"),
                  "validation_schema": report["schema_version"],
                  "supplement_sha256": {path.name: sha256_file(path) for path in supplements}},
    )
    (run_dir / "bronze_manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def validate_reference(*, payload, run_dir, input_path, config, model_route):
    """Use the shared full gate; reference miners cannot self-certify through preflight."""
    from validator.scientific_result_v1.engine import validate
    from validator.scientific_result_v1.sources import SourceBundle
    from validator.scientific_result_v1.source_review import ReviewRuntime
    documents = json.loads((run_dir / "source_payload.json").read_text())["documents"]
    if config.scientific_vision:
        for index, document in enumerate(documents, 1):
            document['images'] = [{'path':str(path.resolve()), 'sha256':sha256_file(path),
                                   'page':int(path.stem.rsplit('-', 1)[-1])}
                                  for path in sorted((run_dir / 'parsed' / f'S{index:03d}').glob('page-*.png'))]
    bundle = SourceBundle(config.paper_id, sha256_file(input_path), tuple(documents))
    runtime = ReviewRuntime(model=config.model, api_key=config.api_key, api_base=config.api_base,
                            model_route=model_route, max_tokens=config.max_tokens,
                            reasoning_effort="none", request_deadline=config.scientific_request_deadline,
                            transport_retries=0)
    return validate(payload, run_dir, sources=bundle, runtime=runtime, expected_paper_id=config.paper_id,
                    expected_pdf_sha256=sha256_file(input_path), scope="reference_preflight",
                    report_dir=run_dir / "reference-validation")
