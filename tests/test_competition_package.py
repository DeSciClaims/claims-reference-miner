import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from claims_reference_miner.competition_build import build
from claims_reference_miner import competition_entrypoint


ROOT = Path(__file__).resolve().parents[2]
CLAIMS = ROOT / "Claims"
PROFILE = ROOT / "infra" / "config" / "competition" / "reference-package" / "testnet.json"


def test_build_contains_pinned_extractor_and_worker_contract(tmp_path: Path):
    output = tmp_path / "dist"
    receipt = build(claims_repo=CLAIMS, profile_path=PROFILE, output_dir=output,
                    build_python=Path(shutil.which("python") or sys.executable),
                    allow_dirty=True)
    wheel = output / receipt["wheel_filename"]
    manifest = json.loads((output / "competition_manifest.json").read_text())
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == receipt["wheel_sha256"]
    assert manifest["entrypoint"] == "claims_reference_miner.competition_entrypoint:main"
    assert manifest["models"] == ["deepseek/deepseek-v4-flash-0731"]
    with zipfile.ZipFile(wheel) as archive:
        assert "miner/agent_v1/runner.py" in archive.namelist()
        assert "miner/agent_v1/skills/compiler/SKILL.md" in archive.namelist()
        assert "claims_reference_miner/competition_profile.json" in archive.namelist()
        packaged = json.loads(archive.read("claims_reference_miner/competition_build_info.json"))
        assert packaged["claims_commit"] == subprocess.check_output(
            ["git", "-C", str(CLAIMS), "rev-parse", "HEAD"], text=True,
        ).strip()


def test_entrypoint_runs_once_with_scoped_gateway_and_writes_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.syspath_prepend(str(CLAIMS))
    from miner.agent_v1.artifact_models import Artifact
    from miner.agent_v1 import runner as canonical_runner

    profile = tmp_path / "competition_profile.json"
    profile.write_bytes(PROFILE.read_bytes())
    monkeypatch.setattr(competition_entrypoint, "files", lambda _name: tmp_path)
    monkeypatch.setenv("CLAIMS_INFERENCE_BASE_URL", "http://gateway.test/v1")
    monkeypatch.setenv("CLAIMS_INFERENCE_TOKEN", "paper-scoped-token")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": "claims_competition_request_v1",
        "paper": {"paper_id": "paper-1", "title": "A paper"},
        "pdf_path": "paper.pdf",
        "inference": {
            "model": "deepseek/deepseek-v4-flash-0731",
            "allowed_models": ["deepseek/deepseek-v4-flash-0731"],
            "max_output_tokens": 8192,
        },
    }))
    source = {"source_id": "s1", "source_type": "span", "span_ids": ["s1"],
              "quote": "An observed result", "role": "result"}
    artifact = Artifact.model_validate({
        "ara_version": "1.0",
        "paper": {"paper_id": "paper-1", "title": "A paper"},
        "logic": {"claims": [{
            "claim_id": "C1", "statement": "An observed result",
            "conditions": "In the paper", "status": "supported",
            "falsification_criteria": "A contradictory observation",
            "proof": ["E1"], "evidence_ids": ["EV1"], "sources": [source],
        }], "experiments": [{
            "experiment_id": "E1", "title": "An experiment", "verifies": ["C1"],
            "setup": "A setup", "procedure": "A procedure",
            "expected_outcome": "An observed result", "evidence_ids": ["EV1"],
            "source_refs": [source],
        }]},
        "evidence": {"records": [{
            "evidence_id": "EV1", "title": "Evidence", "role": "support",
            "summary": "An observed result", "source_refs": [source],
            "linked_claim_ids": ["C1"],
        }]},
        "trace": {"node_id": "root", "node_type": "extraction",
                  "summary": "An observed result", "source_refs": [source]},
        "src": {"environment": ["reference"], "artifacts": []},
    })
    calls = []

    def fake_run(self, pdf_path, *, output_dir, paper_override):
        calls.append((pdf_path, output_dir, paper_override, self.config))
        return artifact

    monkeypatch.setattr(canonical_runner.AgentV1Runner, "run_from_pdf", fake_run)
    output = tmp_path / "result" / "output.json"
    competition_entrypoint.run(request, output)
    assert len(calls) == 1
    assert calls[0][0] == pdf
    assert calls[0][3].api_key == "paper-scoped-token"
    assert calls[0][3].api_base == "http://gateway.test/v1"
    assert calls[0][3].model == "openrouter/openrouter/deepseek/deepseek-v4-flash-0731"
    assert calls[0][3].max_tokens == 8192
    assert json.loads(output.read_text())["metadata"]["reference_release_id"] == "reference-v0"

    payload = json.loads(request.read_text())
    payload["inference"]["model"] = "deepseek/deepseek-v4.1-flash-1017"
    request.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="reference model differs"):
        competition_entrypoint.run(request, output)
    assert len(calls) == 1
