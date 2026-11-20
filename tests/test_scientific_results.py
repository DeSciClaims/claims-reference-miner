import json
import sys
from types import SimpleNamespace

import pytest

from claims_reference_miner.config import ReferenceMinerConfig
from claims_reference_miner.scientific_results import run_scientific_reference


def install_fake_pipeline(monkeypatch, *, complete=True):
    def extract_pdf(pdf, directory, **kwargs):
        directory.mkdir()
        payload = {"tables": [{"csv_file": "P1.E001.T001.csv"}]}
        (directory / "extraction.json").write_text(json.dumps(payload))
        (directory / "P1.E001.T001.csv").write_text("estimate\n-2.5\n")
        (directory / "source_payload.json").write_text("{}")
        return payload
    monkeypatch.setitem(sys.modules, "miner.scientific_result_v1.pipeline", SimpleNamespace(extract_pdf=extract_pdf))
    monkeypatch.setitem(sys.modules, "miner.scientific_result_v1.runtime", SimpleNamespace(DspyRuntime=lambda **kwargs: object()))
    def validate_reference(**kwargs):
        directory = kwargs["run_dir"] / "reference-validation"
        directory.mkdir()
        report = {"submission_ready": complete, "schema_version": "claims_scientific_validation_v1"}
        (directory / "validation_report.json").write_text(json.dumps(report))
        return report
    monkeypatch.setattr("claims_reference_miner.scientific_results.validate_reference", validate_reference)


def config(tmp_path):
    return ReferenceMinerConfig(claims_repo=tmp_path, output_dir=tmp_path / "outputs",
        output_schema="scientific_result_v1.1", runtime="dspy-predict", pdf_reader="docling",
        paper_id="P1", api_key="test-key")


def test_reference_manifest_hashes_json_and_csv_companions(monkeypatch, tmp_path):
    install_fake_pipeline(monkeypatch)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    output = tmp_path / "run"
    manifest = run_scientific_reference(input_path=pdf, input_kind="pdf", output_dir=output,
        config=config(tmp_path), supplements=[], release_lock_sha256=None)
    assert set(manifest.metadata["package_files"]) == {"extraction.json", "P1.E001.T001.csv"}
    assert manifest.metadata["output_schema"] == "scientific_result_v1.1"
    assert (output / "bronze_manifest.json").exists()


def test_incomplete_extraction_cannot_emit_bronze_manifest(monkeypatch, tmp_path):
    install_fake_pipeline(monkeypatch, complete=False)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="not submission-ready"):
        run_scientific_reference(input_path=pdf, input_kind="pdf", output_dir=output,
            config=config(tmp_path), supplements=[], release_lock_sha256=None)
    assert not (output / "bronze_manifest.json").exists()


def test_reference_rejects_incompatible_runtime(monkeypatch, tmp_path):
    install_fake_pipeline(monkeypatch)
    settings = config(tmp_path)
    settings.runtime = "dspy-react"
    with pytest.raises(ValueError, match="dspy-predict"):
        run_scientific_reference(input_path=tmp_path / "paper.pdf", input_kind="pdf", output_dir=None,
            config=settings, supplements=[], release_lock_sha256=None)


def test_reference_passes_native_reasoning_setting_to_dspy(monkeypatch, tmp_path):
    install_fake_pipeline(monkeypatch)
    seen = {}
    def runtime(**kwargs):
        seen.update(kwargs)
        return object()
    monkeypatch.setitem(sys.modules, 'miner.scientific_result_v1.runtime', SimpleNamespace(DspyRuntime=runtime))
    settings = config(tmp_path)
    settings.scientific_reasoning_effort = 'none'
    pdf = tmp_path/'paper.pdf'
    pdf.write_bytes(b'pdf')
    run_scientific_reference(input_path=pdf, input_kind='pdf', output_dir=tmp_path/'run',
        config=settings, supplements=[], release_lock_sha256=None)
    assert seen['reasoning_effort'] == 'none'
