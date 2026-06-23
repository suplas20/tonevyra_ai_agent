# T-024 Batch Processing and Photo Set Consistency Harness Contract

## Required Files

```text
skills/batch-photo-processing/SKILL.md
skills/photo-set-consistency/SKILL.md
harness/schemas/t024_batch_job.schema.json
harness/schemas/t024_set_consistency_result.schema.json
harness/fixtures/t024_batch_set/
harness/scripts/verify_t024_batch_set.py
```

## Contract

- batch_id, set_id, job_id, and attempt_id are distinct scopes.
- Default MVP chunk size is 10.
- Each photo keeps independent quality and retry state.
- Partial failure does not erase or automatically stop valid remaining items.
- Resume is idempotent and does not repeat completed apply/export work.
- Set baselines use bounded relative targets; outliers are protected.
- Strict evidence includes a real multi-photo run and restart/resume proof.
- T-019 through T-023 regressions remain mandatory.
