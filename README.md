# claims-reference-miner

Private Claims reference miner implementation.

This project produces **Bronze** records for the SN111 Claims validator loop.
It intentionally lives outside the public `Claims` repo because the reference
pipeline can use private prompts, stronger models, and internal repair logic.

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

The CLI delegates to the public `miner.agent_v1` runner but applies private
reference-miner configuration and writes a Bronze manifest.

## Environment

```text
CLAIMS_REFERENCE_MINER_CLAIMS_REPO=../Claims
CLAIMS_REFERENCE_MINER_OUTPUT_DIR=outputs
CLAIMS_REFERENCE_RELEASE_ID=reference-v0
CLAIMS_REFERENCE_PROFILE_ID=reference-agent-v1-strong
CLAIMS_REFERENCE_MINER_RUNTIME=dspy-react
CLAIMS_REFERENCE_MINER_HARNESS=dspy-react
CLAIMS_REFERENCE_MINER_MODEL=openrouter/openai/gpt-5
CLAIMS_REFERENCE_MINER_PDF_READER=pdf-inspector
OPENROUTER_API_KEY=...
```

For a CLI-backed reference miner, keep `runtime=agent-cli`, set the wrapper as
the CLI command, and put the actual external agent command in the inner command:

```text
CLAIMS_REFERENCE_MINER_RUNTIME=agent-cli
CLAIMS_REFERENCE_MINER_HARNESS=hermes-cli
CLAIMS_REFERENCE_MINER_CLI_COMMAND="python -m miner.agent_v1.wrappers.hermes_prompt"
CLAIMS_REFERENCE_MINER_INNER_COMMAND="hermes chat --provider openrouter -m openai/gpt-5-mini --max-turns 30 -q"
CLAIMS_REFERENCE_MINER_MODEL=openai/gpt-5-mini
```
