# Independent evaluation

Q-Batch verification and response-quality evaluation are separate stages.

1. Run the experiment. Q-Batch checks evidence integrity and paired-run instrumentation.
2. Export a blinded packet. The packet contains task prompts and responses under opaque IDs. It does not contain condition labels, resource files, or the intervention mapping.
3. Give the scorer only the packet and the predeclared rubric. Keep the private key in the controller's custody.
4. Lock the scores. The scorer returns one score per sample and criterion.
5. Run the evaluator with the private key. It resolves opaque IDs to A/B only after scoring is complete and calculates descriptive paired differences.

The evaluator does not call a model or infer scores from response text. It accepts externally supplied scores only.

## Blinded export

```bash
aier blind-export \
  --report path/to/experiment/reports/batch-report.json \
  --spec path/to/experiment.json \
  --packet scorer/scoring-packet.json \
  --private-key controller/blind-key.json
```

Share only `scoring-packet.json` and the rubric with the evaluator. Never share `blind-key.json` or raw Q-Batch run directories with the scorer. The packet shuffles sample order and replaces run IDs with random opaque IDs. The battery runner also randomises which A/B label is assigned to baseline and skill-enabled for each experiment; that mapping stays in the private controller key.

## Rubric format

```json
{
  "criteria": [
    {
      "id": "task_accuracy",
      "description": "Correctness against the task's verifiable requirements",
      "min_score": 0,
      "max_score": 4,
      "anchors": {
        "0": "Incorrect or unsupported",
        "2": "Partially correct with material omissions",
        "4": "Correct and complete"
      }
    }
  ]
}
```

## Score sheet format

The rubric and private-key hashes use SHA-256 over canonical JSON (UTF-8, sorted keys, compact separators). The report hash binds scores to the exact experiment specification. The evaluator receives the score sheet and private key only after the scorer has locked its judgements.

```json
{
  "experiment_id": "example",
  "report_spec_sha256": "COPY_FROM_SCORING_PACKET",
  "rubric_sha256": "SHA256_OF_CANONICAL_RUBRIC",
  "blind_key_sha256": "CONTROLLER_SUPPLIES_AFTER_SCORING",
  "evaluator_id": "reviewer-01",
  "scores": [
    {"blind_id": "sample-opaque-id", "values": {"task_accuracy": 3}}
  ]
}
```

Evaluation command:

```bash
aier evaluate \
  --report path/to/batch-report.json \
  --rubric path/to/rubric.json \
  --scores path/to/scores.json \
  --private-key controller/blind-key.json \
  --output evaluation.json
```

Every completed run must have exactly one score for every rubric criterion. Duplicate, missing, unknown, non-finite, or out-of-range scores are rejected. The evaluation output reveals the condition mapping only after scoring and reports baseline/skill-enabled means plus paired skill-minus-baseline differences by criterion.

These are descriptive summaries. The runtime does not calculate significance, confidence intervals, or causal effects. Repeated trials are not automatically independent samples, and evaluator agreement/reliability must be handled by the evaluation protocol.
