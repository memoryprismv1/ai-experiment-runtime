# Q-Batch integration contract

Q-Batch is the independently maintained evidence method and verifier. This runtime uses it rather than copying or reimplementing its logger.

## Pin

The bootstrap script and CI workflow pin `memoryprismv1/q-batch-of-evidence` to:

`c059f5d5f969edcc7a87e7e288956a39c945cdc8`

The runtime imports:

- `testing_logger.logger.TestingLogger`, `LOGGER_VERSION`, `SCHEMA_VERSION`, and `utc_now`;
- `experiments.ct_ab.validate_log.validate_run`;
- `experiments.ct_ab.validate_log.validate_pair`.

The generic `TestingLogger` is used, not the CT-specific `RunLogger`, whose manifest validation includes CT pilot context requirements. Q-Batch's general validator accepts a minimal manifest with no context record.

## Verification

Each trial manifest includes the fields required by Q-Batch's run validator: run ID, blind condition label, task and condition hashes, logger/schema versions, timestamp, model, environment, resource limits, and a declared base identity. The event stream records model request/response capture and evidence artifacts through Q-Batch's logger.

`validate_run` checks the run record and its evidence references. `validate_pair` is called with the minimum event set relevant to this text adapter (`run_started`, `run_finished`, `model_request`, `model_response`). The Q-Batch pair validator additionally checks matching controlled fields between A and B.

A Q-Batch `PASS` means the captured evidence passed the verifier's integrity and pairing checks. It is not a quality score. If a provider or condition differs on a field Q-Batch treats as controlled, pair validation should fail or be treated as not comparable; do not weaken the validator just to obtain a green result.

## Updating the pin

Update the pin only as a deliberate compatibility change. Run the runtime tests against the new Q-Batch revision, record the tested SHA in both `setup_environment.py` and `.github/workflows/tests.yml`, and update this document. No automatic `main` tracking is used.
