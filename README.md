# claims-reference-miner

Claims reference miner implementation.

This project produces **Bronze** records for the SN111 Claims validator loop.
It lives outside the main `Claims` repository so the reference release can be
versioned independently while reusing the canonical public extraction pipeline.

The output contract is public and stable:

- `agent_output.json`: a standard `agent_v1` artifact.
- `source_payload.json`: source spans used to ground the artifact.
- `bronze_manifest.json`: reference metadata, hashes, version IDs, and paths.

## CLI

```bash
claims-reference-miner \
  --text /path/to/paper.txt \
  --output-dir outputs/paper-001 \
  --claims-repo ../Claims \
  --reference-release-id reference-v0
```

For PDF input, the default reader is `pdf-inspector`:

```bash
claims-reference-miner \
  --pdf /path/to/paper.pdf \
  --pdf-reader pdf-inspector \
  --output-dir outputs/paper-001 \
  --claims-repo ../Claims
```

For local development without installing the package:

```bash
PYTHONPATH=. python -m claims_reference_miner \
  --text /path/to/paper.txt \
  --output-dir outputs/paper-001 \
  --claims-repo ../Claims
```

The CLI delegates to the public `miner.agent_v1` runner, applies the selected
reference model/runtime configuration, and writes a Bronze manifest.

For a frozen competition release, set `CLAIMS_REFERENCE_RELEASE_LOCK` to a
JSON file containing `schema_version: claims_reference_release_v1`, the full
`claims_commit`, `reference_miner_source_sha256`, and the runtime fields listed
in `claims_reference_miner/release_lock.py`. Once the model and Claims commit
are selected, generate a candidate lock with the intended runtime environment:

```sh
python -m claims_reference_miner.release_lock \
  --claims-repo ../Claims --output reference-release.json
```

The command refuses a dirty Claims extraction checkout and will not overwrite
an existing lock. Set `CLAIMS_REFERENCE_RELEASE_LOCK=reference-release.json`
for Bronze production. The runner then checks the Claims commit, relevant
working tree, reference miner source/build hash, model, reader, and inference
settings before extraction, and records the lock hash in each Bronze manifest.
Leave this variable unset only for development runs. The actual week-one lock
is published after the reference model and Claims release are selected.
Changing the reference model requires a new release lock and Bronze records;
an existing locked release remains fixed.

The reference runner also accepts `CLAIMS_INFERENCE_BASE_URL` and
`CLAIMS_INFERENCE_TOKEN`. When supplied, these take precedence over direct
OpenRouter credentials so a reference run can use a scoped Bifrost key.

## Competition baseline package

The competition worker uses a separate wheel built from this repository and a
pinned Claims extraction checkout. It carries the canonical `miner.agent_v1`
code and compiler skill, and accepts the worker's `--request` and `--output`
arguments. The worker supplies a paper-scoped gateway key at run time; neither
the upstream OpenRouter key nor a gateway administrator key is packaged.

From `infra/`, build the wheel with the network's reviewed reference profile:

```sh
PYTHONPATH=../claims-reference-miner python -m claims_reference_miner.competition_build \
  --claims-repo ../Claims \
  --profile config/competition/reference-package/testnet.json \
  --output-dir .local/reference-competition-testnet
```

The output contains a wheel, a competition
manifest, and a build receipt with source hashes. Build on Linux with the same
Python version and architecture as the worker; its offline wheelhouse needs
the dependencies listed in `infra/templates/competition-worker-requirements.txt`.
The competition runner uses pinned V4 Flash and the same `agent_v1` extraction
code, PDF reader, and compiler skill as the Bronze runner. Confirm the profile
matches the published Bronze release lock before sealing the wheel for a round.

## Skill

The reference miner uses the canonical compiler skill from the configured
`Claims` checkout:

```text
miner/agent_v1/skills/compiler/SKILL.md
```

Set `CLAIMS_REFERENCE_MINER_CLAIMS_REPO` or pass `--claims-repo` to identify
that checkout. `SUBNET_CLAIMS_AGENT_SKILL_DIR` can override the compiler skill
for controlled experiments; there is no separate private reference skill.
Use Python 3.11 or newer; the reference process imports the Claims validator
runtime and therefore shares its Python requirement.

## Environment

```text
CLAIMS_REFERENCE_MINER_CLAIMS_REPO=../Claims
CLAIMS_REFERENCE_MINER_OUTPUT_DIR=outputs
CLAIMS_REFERENCE_RELEASE_ID=reference-v0
CLAIMS_REFERENCE_PROFILE_ID=reference-agent-v1-strong
CLAIMS_REFERENCE_MINER_RUNTIME=dspy-react
CLAIMS_REFERENCE_MINER_HARNESS=dspy-react
CLAIMS_REFERENCE_MINER_MODEL=deepseek/deepseek-v4-flash-0731
CLAIMS_REFERENCE_MINER_PDF_READER=pdf-inspector
OPENROUTER_API_KEY=...
```

For a CLI-backed reference miner, keep `runtime=agent-cli`, set the wrapper as
the CLI command, and put the actual external agent command in the inner command:

```text
CLAIMS_REFERENCE_MINER_RUNTIME=agent-cli
CLAIMS_REFERENCE_MINER_HARNESS=hermes-cli
CLAIMS_REFERENCE_MINER_CLI_COMMAND="python -m miner.agent_v1.wrappers.hermes_prompt"
CLAIMS_REFERENCE_MINER_INNER_COMMAND="hermes chat --provider openrouter -m deepseek/deepseek-v4-flash-0731 --max-turns 30 -q"
CLAIMS_REFERENCE_MINER_MODEL=deepseek/deepseek-v4-flash-0731
```
