"""Build a self-contained reference competition wheel from a pinned Claims checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROFILE_FIELDS = {
    "reference_release_id", "reference_profile_id", "runtime", "model",
    "pdf_reader", "temperature", "max_tokens", "max_agent_iters",
    "max_repair_attempts",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _profile(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("schema_version") != "claims_reference_competition_profile_v1"
        or set(value) != PROFILE_FIELDS | {"schema_version"}
        or value.get("runtime") != "dspy-react"
        or value.get("pdf_reader") not in {"pdf-inspector", "pypdf"}
        or not isinstance(value.get("model"), str) or not value["model"]
        or value["model"].startswith("openrouter/")
        or any(not isinstance(value.get(key), str) or not value[key]
               for key in ("reference_release_id", "reference_profile_id"))
        or any(type(value.get(key)) is not int or not 1 <= value[key] <= 32768
               for key in ("max_tokens", "max_agent_iters", "max_repair_attempts"))
        or type(value.get("temperature")) not in {int, float}
        or not math.isfinite(value["temperature"])):
        raise ValueError("invalid reference competition profile")
    return value


def build(*, claims_repo: Path, profile_path: Path, output_dir: Path,
          build_python: Path = Path(sys.executable), allow_dirty: bool = False) -> dict[str, Any]:
    reference_repo = Path(__file__).resolve().parents[1]
    extraction_dir = claims_repo / "miner" / "agent_v1"
    if not (extraction_dir / "runner.py").is_file():
        raise ValueError("Claims checkout has no canonical agent_v1 extractor")
    if _git(claims_repo, "status", "--porcelain", "--", "miner/agent_v1"):
        raise ValueError("Claims extraction checkout must be clean")
    reference_dirty = bool(_git(reference_repo, "status", "--porcelain", "--untracked-files=all"))
    if reference_dirty and not allow_dirty:
        raise ValueError("reference miner checkout must be committed before a release build")
    profile = _profile(profile_path)
    claims_commit = _git(claims_repo, "rev-parse", "HEAD")
    reference_commit = _git(reference_repo, "rev-parse", "HEAD")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite package output: {output_dir}")
    with tempfile.TemporaryDirectory(prefix="claims-reference-build-") as temporary:
        stage = Path(temporary)
        package_dir = stage / "claims_reference_miner"
        miner_dir = stage / "miner"
        shutil.copytree(
            reference_repo / "claims_reference_miner", package_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "competition_profile.json", "competition_build_info.json"),
        )
        miner_dir.mkdir()
        shutil.copy2(claims_repo / "miner" / "__init__.py", miner_dir / "__init__.py")
        shutil.copytree(
            extraction_dir, miner_dir / "agent_v1",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pdf", "outputs", ".cache"),
        )
        (package_dir / "competition_profile.json").write_text(
            json.dumps(profile, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8",
        )
        build_info = {
            "schema_version": "claims_reference_competition_build_v1",
            "claims_commit": claims_commit,
            "reference_commit": reference_commit,
            "reference_source_clean": not reference_dirty,
            "claims_extraction_sha256": _tree_sha256(extraction_dir),
            "reference_source_sha256": _tree_sha256(reference_repo / "claims_reference_miner"),
            "profile_sha256": _sha256(profile_path),
        }
        (package_dir / "competition_build_info.json").write_text(
            json.dumps(build_info, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8",
        )
        (stage / "pyproject.toml").write_text(
            """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "claims-reference-competition"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["dspy==3.1.2", "pdf-inspector==0.2.6", "pydantic>=2,<3"]

[tool.setuptools.packages.find]
include = ["claims_reference_miner*", "miner*"]

[tool.setuptools.package-data]
claims_reference_miner = ["competition_profile.json", "competition_build_info.json"]
"miner.agent_v1" = ["skills/compiler/*.md", "skills/compiler/*.py", "skills/compiler/references/*.md"]
""", encoding="utf-8",
        )
        output_dir.mkdir(parents=True)
        subprocess.run(
            [str(build_python), "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
             "--wheel-dir", str(output_dir), str(stage)], check=True,
        )
    wheels = list(output_dir.glob("claims_reference_competition-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("reference package build produced no unique wheel")
    wheel = wheels[0]
    manifest = {
        "schema_version": "claims_competition_manifest_v1",
        "package_format": "wheel", "package_filename": wheel.name,
        "language": "python", "team_id": "claims-reference",
        "entrypoint": "claims_reference_miner.competition_entrypoint:main",
        "source_included": True, "license_production_use": True,
        "models": [profile["model"]],
    }
    (output_dir / "competition_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    receipt = {**build_info, "wheel_sha256": _sha256(wheel), "wheel_filename": wheel.name}
    (output_dir / "build_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-repo", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable),
                        help="Build Python with pip, setuptools, and wheel installed")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="Local development only; build receipt marks source as dirty")
    args = parser.parse_args()
    print(json.dumps(build(
        claims_repo=args.claims_repo.resolve(), profile_path=args.profile.resolve(),
        output_dir=args.output_dir.resolve(), build_python=args.python.resolve(),
        allow_dirty=args.allow_dirty,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
