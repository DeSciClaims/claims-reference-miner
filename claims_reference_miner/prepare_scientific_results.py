"""Prepare Docling sources for v1.1 development without producing Bronze records."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .runner import _ensure_claims_importable


def prepare_pdf(*, pdf_path: Path, output_dir: Path, claims_repo: Path) -> dict:
    if not pdf_path.is_file():
        raise ValueError(f"PDF does not exist: {pdf_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Use an empty output directory to avoid mixing source exports")
    _ensure_claims_importable(claims_repo.resolve())
    from miner.scientific_result_v1.docling_source import parse_pdf
    from miner.scientific_result_v1.schema import schema_path

    # Resolve the contract before performing an expensive document conversion.
    schema_bytes = schema_path(claims_repo.resolve()).read_bytes()
    source = parse_pdf(pdf_path.resolve(), output_dir)
    (output_dir / "extraction_schema.json").write_bytes(schema_bytes)
    receipt = {
        "schema_version": "claims_scientific_result_preparation_v1",
        "output_schema_version": "1.1",
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "source_sha256": source["source_sha256"],
        "parser": source["parser"],
        "stage": "source_preparation_only",
    }
    (output_dir / "preparation_manifest.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--claims-repo", required=True, type=Path)
    args = parser.parse_args()
    prepare_pdf(pdf_path=args.pdf, output_dir=args.output_dir, claims_repo=args.claims_repo)


if __name__ == "__main__":
    main()
