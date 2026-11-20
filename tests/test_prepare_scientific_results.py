
import pytest
from claims_reference_miner.prepare_scientific_results import prepare_pdf


def test_preparation_refuses_to_mix_existing_outputs(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"PDF")
    output = tmp_path / "run"
    output.mkdir()
    existing = output / "agent_output.json"
    existing.write_text("existing bronze artifact")
    with pytest.raises(ValueError, match="empty output"):
        prepare_pdf(pdf_path=pdf, output_dir=output, claims_repo=tmp_path)
    assert existing.read_text() == "existing bronze artifact"


def test_preparation_rejects_missing_pdf(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        prepare_pdf(pdf_path=tmp_path / "missing.pdf", output_dir=tmp_path / "run", claims_repo=tmp_path)
