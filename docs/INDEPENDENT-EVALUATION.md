# Independent evaluation

Q-Batch verification and quality evaluation are separate stages.

1. Run the experiment and verify its evidence with Q-Batch.
2. Prepare a rubric before inspecting the condition outputs. Use observable criteria, explicit score ranges, and anchored descriptions.
3. Give an evaluator the responses under blind run IDs/labels. Keep the controller condition key separate until scoring is complete.
4. Record one score per run per criterion in a score sheet.
5. Run `aier evaluate` to validate completeness and calculate descriptive paired differences.

The evaluator does not call a model, infer scores from response text, or decide which condition is better. It accepts externally supplied scores only.

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

The rubric hash is SHA-256 over canonical JSON (UTF-8, sorted keys, compact separators). The report hash binds scores to the exact experiment specification.

```json
{
  "experiment_id": "example",
  "report_spec_sha256": "COPY_FROM_BATCH_REPORT",
  "rubric_sha256": "SHA256_OF_CANONICAL_RUBRIC",
  "evaluator_id": "reviewer-01",
  "scores": [
    {"run_id": "RUN_ID_FROM_REPORT", "values": {"task_accuracy": 3}}
  ]
}
```

Every completed run must have exactly one score for every rubric criterion. Duplicate, missing, unknown, non-finite, or out-of-range scores are rejected. The evaluation output reports per-condition means and paired B-minus-A differences by criterion.

These are descriptive summaries. The runtime does not calculate significance, confidence intervals, or causal effects. Repeated trials are not automatically independent samples, and evaluator agreement/reliability must be handled by the evaluation protocol. Preserve the blind until scoring is locked; the generated evaluation file intentionally retains A/B labels rather than resolving the condition key.
