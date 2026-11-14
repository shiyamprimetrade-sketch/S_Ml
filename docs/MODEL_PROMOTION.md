# Model promotion gate - version 0.3

Training creates a candidate. It does not change the active model. The new
`promotion.train_and_gate` path trains, saves, registers and evaluates prepared
regression data; activation occurs only inside the persistent promotion gate.
The existing public benchmark remains an isolated experiment and never writes
an active production model.

## Default acceptance policy

| Check | Requirement |
|---|---|
| Holdout size | At least 30 distinct observations |
| Mean absolute error (MAE) | More than 5% lower than both the training-mean baseline and current active model |
| Absolute gain | MAE decrease greater than 1e-8 target units to avoid numerical-noise promotions |
| Root mean squared error (RMSE) | No increase against either reference |
| Data separation | No evaluation IDs in candidate or incumbent training data |
| Fresh evaluation evidence | IDs previously scored in this mission cannot be reused, even after rejection |
| Feature contract | Same named, ordered feature schema as the incumbent |
| Temporal validity | Forecast origins after both models' training-label cutoffs; origins sorted; outcomes available by evaluation time and after their origins |
| Artifact integrity | Supported numeric JSON format and stored SHA-256 match |

The baseline is computed from candidate training targets, never from held-out
outcomes. Candidate, baseline and incumbent are scored on the same rows. With no
incumbent, beating the baseline is still required. Rejection preserves the active
pointer; if no model has been approved, the registry remains empty and the caller
must use its baseline or abstain. No arbitrary checkpoint is activated by default.

Thirty observations and a 5% gain are engineering defaults, not proof of
statistical significance or a guarantee of future quality. Correlation, drift,
small samples and changing platform behavior still matter. Tune policy before
looking at a gate batch; do not lower thresholds to rescue a rejected candidate.
For final quality auditing, reserve another dataset never used for promotion.

## Prepared training interface

```bash
python -m s_ml train-and-gate private/prepared_training.json
python -m s_ml model-status
python -m s_ml model-rollback YOUR_MISSION PREVIOUS_APPROVED_VERSION
```

The prepared JSON manifest uses schema `s_ml.training-gate.v1`:

| Field | Meaning |
|---|---|
| mission | Stable target definition, including forecast horizon and target unit where applicable |
| version | New immutable candidate version; never reuse it for changed weights/data |
| account_id | Required for account-derived models so export/deletion can follow ownership |
| validation_mode | `temporal` by default; `iid` only for explicitly independent laboratory datasets |
| parameters | Optional supported LinearGD parameters |
| training.x / training.y | Finite feature matrix and one target per row |
| training.ids | Unique stable observation IDs |
| training.feature_schema | Ordered feature names matching matrix columns |
| training.label_available_until | Last training-label availability timestamp, required for temporal models |
| evaluation.x / evaluation.y | Separate held-out feature matrix and actual outcomes |
| evaluation.ids | Distinct IDs not seen in training or earlier scored gate batches |
| evaluation.prediction_at | Forecast-origin timestamps in chronological order, required for temporal models |
| evaluation.label_available_at | Actual outcome availability timestamps, required for temporal models |

All timestamps must include timezone. Account-linked models cannot opt into iid
validation. Mission ownership and validation mode cannot change between versions.
The caller must preserve the source dataset and manifest privately to reproduce
training; checkpoint parameters, scaling and weights are saved. Dataset identity,
cutoffs, provider freshness, forecast horizon and stable IDs are a provenance
boundary: the gate cannot discover undeclared training exposure, IDs relabelled
as new examples, or invented timestamps. Do not turn undated lifetime platform
snapshots into forecast targets. No live TikTok promotion is claimed.

A prepared-data scheduler can invoke `train_and_gate` automatically. The current
export-inbox worker does not assemble training labels or launch training from raw
post exports; that collector/label-readiness integration remains unfinished.

## Persistent activation and recovery

SQLite schema v3 adds immutable checkpoint snapshots, active pointers, decision
reports and consumed holdout IDs. The artifact is copied into the registry, so
changing a candidate file does not mutate the active model. Decisions, consumed
samples and pointer changes commit in one transaction under an exclusive write
claim. An injected database failure rolls all three back. A second evaluator
reads the current incumbent after acquiring that transaction, preventing a stale
comparison from overwriting a newer promotion.

`active_model(store, mission)` returns only the selected checkpoint and version,
or None. Prediction adapters must resolve that pointer rather than loading the
most recently trained file. No live TikTok forecast adapter currently exists.
`registry_status` and the dashboard expose active versions and decision counts;
the CLI also returns the most recent reasons.

Rollback requires a named version that previously passed promotion. It verifies
the stored artifact digest and records the previous/target versions atomically.
It cannot activate an untested candidate. Account deletion cascades to linked
registry data; independently saved candidate files, exports and backups still
require separate deletion.

## Reproducible verification

After installing the package:

```bash
python -m unittest discover -s tests -v
python scripts/demo_promotion_gate.py
```

The demonstration uses deliberately constructed training targets and fresh
synthetic holdouts to exercise acceptance/rejection. It is a control-flow test,
not a platform or general forecasting accuracy result. The committed report is
`reports/promotion_gate_control.json`: initial -> accepted, better -> accepted,
worse -> rejected, active model retained, explicit rollback verified.

Tests cover baseline/incumbent comparison, lower MAE but worse RMSE, insufficient
data, overlap, holdout reuse, missing/future/invalid temporal ordering, immutable
versions, restart persistence, atomic failure recovery, account deletion,
feature mismatch, training/checkpoint/evaluation integration and rollback.
