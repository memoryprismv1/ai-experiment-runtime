# Architecture

## Design

The runtime separates five responsibilities:

1. **Experiment definition** — frozen tasks, conditions, resources, provider settings, trial count, and declared comparison.
2. **Subject/provider adapter** — how a test subject receives a task and returns an output. The current adapter is text chat; provider-independent execution is kept behind `call_provider`.
3. **Trial controller** — creates a fresh workspace and evidence directory for each task × condition × repetition.
4. **Evidence recorder** — uses Q-Batch's `TestingLogger` directly from the pinned Q-Batch checkout. It does not recreate Q-Batch's JSONL event chain or artifact hashing.
5. **Verifier/report** — calls Q-Batch's `validate_run` and `validate_pair`; reports evidence validity separately from response quality.

## Extending beyond text and skills

A new subject adapter should own its input/output contract, environment requirements, capture points, reset protocol, and safety boundaries. Examples of future adapters include:

- Software task adapters with an independent acceptance suite.
- Image/video adapters with media hashes, frame/time references, and image-capable provider transport.
- Audio adapters with input media and transcription/output evidence.
- Dataset and retrieval experiments.
- Tool-using agents with runner-observed tool dispatch and state snapshots.
- Robotics simulators with declared simulator version, world seed, action traces, and reset state.

A domain adapter must not claim support merely because a text prompt can describe that domain. It must capture the domain's actual inputs, outputs, and relevant state.

## Isolation model

Every trial gets a new workspace. Its evidence is written by the controller into a sibling `runs/` directory, not inside the workspace. The initial runtime does not execute subject-generated code. This gives process-level separation of files and run history; it is not a hardened operating-system sandbox and does not prove that a remote provider has no persistent state.

The manifest records the provider, model ID, Python/runtime identity, task and condition hashes, and resource limits. Missing provider metadata is not inferred. Future adapters should record their own environment and reset facts.

## Reproducibility

The experiment JSON is hashed canonically. Each loaded resource file is hashed by exact bytes. The raw prompt and response are captured as Q-Batch artifacts. The Q-Batch verifier validates event sequencing, event hash chaining, artifact size and digest, and controlled-pair fields. It does not establish that a model is deterministic; provider-side model changes, hidden state, and nondeterministic inference remain possible and must be recorded where known.
