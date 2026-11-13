# AI Experiment Runtime

A general-purpose Python laboratory for controlled experiments on AI systems and workflows.

This repository is independent of any specific skill collection, model, agent, or project. Skills are one kind of experimental intervention—not the runtime's boundary.

## What it is for

Use the runtime to compare a baseline against an intervention while keeping each trial isolated and its evidence traceable. In this first release, interventions are text-based: condition-specific system instructions and UTF-8 resources such as a skill file or reference document. The exact task is presented to both conditions, the provider/model configuration is shared, and the runner repeats trials with randomized A/B execution order.

The initial release includes:

- A versioned JSON experiment format.
- Two-condition, independently logged trials with repeated tasks.
- A provider interface with a deterministic mock provider and an OpenAI-compatible chat-completions provider (including local endpoints such as Ollama's OpenAI-compatible API).
- Hashes for the experiment specification, tasks, and all loaded text resources.
- Fresh trial workspaces and runner-owned evidence directories outside those workspaces.
- Q-Batch's own append-only logger and validator, imported from a pinned checkout. No Q-Batch implementation is copied here.
- Separate reporting of execution completion and Q-Batch evidence verification. Response quality is not inferred from a green instrumentation check.\n- An independent rubric evaluator that accepts external blinded scores and reports descriptive paired differences without self-grading.

## What it does not claim

Q-Batch verifies run records, artifact integrity, and controlled-pair instrumentation. It does not grade a model response, prove a skill is effective, or establish causation. This runtime therefore labels quality scoring as not performed unless a separate evaluator is added. Human or independent evaluation should be done offline against predeclared criteria.

The first provider adapter handles text chat. Future subject adapters can extend the runtime to software, image/video, audio, robotics, dataset/retrieval, and tool-using-agent experiments. Those adapters are not implemented in this initial slice. Neither arbitrary tool execution nor sandboxed code execution is supported.

## Set up

Requirements: Python 3.11+ and Git.

```bash
python setup_environment.py
```

This creates `.venv/`, checks out Q-Batch at the pinned commit recorded in `setup_environment.py`, and installs this package in editable mode. The script refuses to overwrite a modified Q-Batch checkout.

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

The setup has no third-party runtime dependencies. Q-Batch is fetched separately into `.vendor/q-batch-of-evidence/`; the local `Q_BATCH_PATH` environment variable can point to another checkout when needed.

## Run the deterministic verification fixture

```bash
python -m ai_experiment_runtime run \
  --spec examples/deterministic-pair.json \
  --output ./experiment-output/demo
```

The fixture makes no model or network calls. It verifies that two isolated conditions can execute, preserve evidence, and pass Q-Batch run and pair validation. It is a runtime/Q-Batch instrumentation check, **not** an evaluation of AI capability or skill efficacy.

## Run a real model experiment

1. Copy `examples/skill-comparison-template.json` and edit its tasks, provider, resource paths, and conditions.
2. Put the baseline and intervention in separate conditions A and B. Use a pinned skill revision or a local immutable snapshot for any skill file.
3. Configure the provider endpoint and model. For the OpenAI-compatible adapter, set `AI_RUNTIME_API_KEY` (or the environment variable named by `provider.api_key_env`) where required. Do not put credentials in the JSON file.
4. Run into a new, private local output directory:

```bash
python -m ai_experiment_runtime run --spec ./my-experiment.json --output ./private-results/run-001
```

The output contains raw prompts and responses, including condition resources. It must be handled as private experimental evidence even when the source repository is public. Do not upload real prompts, private data, model traces, or condition keys to a public repository or public Actions artifacts.

For a local Ollama OpenAI-compatible endpoint, a provider block can use `http://127.0.0.1:11434/v1` and a locally installed model name. The runtime does not install or download models.

## Output layout

```text
experiment-output/
  runs/
    A/<task>-r01/             # Q-Batch manifest, events, checksums, artifacts
    B/<task>-r01/
  workspaces/
    A/<task>-r01/             # empty, isolated trial workspace
    B/<task>-r01/
  controller/
    condition-key.json        # maps blind labels to condition IDs
  reports/
    batch-report.json        # execution + Q-Batch validation, not quality scoring
```

Each run is a separate evidence batch. Q-Batch validates each run and, where the controlled fields match, the A/B pair. Raw evidence includes the exact system/user prompt sent to the model, response text, provider response, request metadata, and Q-Batch hash chain. Keep the `controller/` directory separate from any blinded assessment material.

## Boundaries

- **Q-Batch remains separate.** This repository pins and imports Q-Batch's logger and verifier; it does not vendor a copy or modify the Q-Batch repository.
- **Skill repositories are test subjects.** The runtime reads supplied skill/resource files and records their hashes. It does not edit canonical skill sources.
- **No self-grading.** An agent's claim that it succeeded is an output, not independent verification.
- **No hidden chain-of-thought capture.** The runtime records requests, responses, declared outputs, and observable evidence only.
- **No sandbox claim.** The initial runtime does not execute model-generated code or arbitrary shell commands. A future execution adapter must define and enforce its own isolation boundary.

## Development

```bash
python -m unittest discover -s tests -v
```

CI checks the Python package, runs the synthetic two-condition experiment, then invokes Q-Batch's own verifier against the produced evidence. The workflow does not call a paid model or upload raw real-model traces.

See [Architecture](docs/ARCHITECTURE.md), [Experiment format](docs/EXPERIMENT-FORMAT.md), [Q-Batch integration](docs/QBATCH-INTEGRATION.md), and [Independent evaluation](docs/INDEPENDENT-EVALUATION.md). The ten-skill paired test battery is documented in [Cognitive skill experiments](experiments/cognitive-skills/README.md).
