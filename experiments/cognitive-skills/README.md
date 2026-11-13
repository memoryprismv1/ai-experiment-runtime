# Cognitive skill experiment battery

This directory contains separate, paired experiments for the ten skills in the canonical `memoryprismv1/cognitive-interface-ai-skills` repository.

Pinned source revision: `fc530b6815eead24aa8655cbbb4bfe0dd8c9f666`.

## Coverage

- Automaticity
- A Touch of Grace
- Critical Thinking
- Context Course Correction
- Good-Faith Collaboration & Approach Calibration
- Peer Review
- Optionality
- Software Literacy for AI Collaboration
- Task Integrity
- Verification Integrity

Each skill has its own experiment spec and predeclared rubric. Each spec uses the same model and shared system prompt in both conditions, with the canonical `SKILL.md` loaded only in the intervention condition. The task set contains three probes per skill, repeated twice: 12 model responses per skill, 120 responses across the full battery.

The battery runner randomly assigns the intervention to A or B for each skill experiment; the mapping is retained only in the private controller key. The scorer receives shuffled opaque sample IDs, task prompts and responses, not the condition label or skill resource. The tasks are behaviour probes, not a test of whether a model can recite the skill. Multi-turn failure modes are represented as frozen transcripts in a single prompt because runtime v1 currently makes one model request per trial. That is a limitation: these probes test response to supplied trajectory changes, not continuous online monitoring during a live conversation.

## Run

The setup script fetches Q-Batch and the skills repository at pinned revisions. The skills checkout is a read-only test subject; this runtime does not modify it.

The default runner uses a local Ollama model (`qwen2.5:3b`) through its OpenAI-compatible local endpoint. It requires no API key, API credits, or external inference account. In GitHub Actions, the workflow installs Ollama, downloads the model, and runs the selected skill automatically. For a local machine, install Ollama and pull the model first:

```bash
ollama pull qwen2.5:3b
ollama serve
python setup_environment.py
python scripts/run_cognitive_skill_battery.py
```

The runner defaults to `qwen2.5:3b` at `http://127.0.0.1:11434/v1`. Override `--model` and `--base-url` to use another local OpenAI-compatible server. Both conditions use the same model, temperature and token limit. The workflow uses a GitHub-hosted runner, so model inference runs on that temporary machine; there is no API billing, although Actions runtime and model-download limits still apply.

The runner produces:
- Q-Batch-verified experiment reports and raw evidence;
- scorer-facing blinded packets and matching rubrics;
- private controller keys required to resolve scores after scoring is locked.

**Do not give the controller directory or raw Q-Batch run directories to the scorer.** Share only each skill's `scorer/scoring-packet.json` and `scorer/rubric.json`. Keep `controller/blind-key.json` private until all scores are locked.

## Interpretation

Q-Batch verifies run/evidence integrity and paired instrumentation. It does not grade skill quality. The rubric evaluator accepts externally supplied scores and reports paired descriptive differences. It does not self-grade, calculate statistical significance, or establish causality.

Two trials per task are a first pilot, not enough to claim a stable effect. The battery is intended to reveal obvious strengths, regressions, and task-specific patterns. A promising result needs more trials, independent evaluators, agreement checks, and possibly a larger task set.

## Known limitations

- Runtime v1 supports two conditions and one model request per task/trial.
- Context Course Correction and Good-Faith probes include transcript snippets; they do not test continuous multi-turn runtime monitoring.
- Some skills are user-activated or contextual. Their rubrics include restraint and user-agency criteria so indiscriminate activation is not rewarded.
- Model/provider version, prompt format and token budget must remain fixed across A/B.
- The canonical skill revision is pinned; changing the skill requires a new experiment ID/revision and fresh reports.
