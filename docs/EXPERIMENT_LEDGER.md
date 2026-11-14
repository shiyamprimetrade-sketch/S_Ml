# Experiment ledger

## E001 - Public regression core, 2026-11-14

Question: can explicit gradient descent learn a reusable regularized regression
model, beat a mean baseline on held-out public observations, and restore exactly?
Dataset: scikit-learn diabetes, 442 real public examples. No TikTok data used.
Fixed index split: 265 training, 88 validation, 89 test. This is not time-series
validation. Dataset hash and exact library versions are in the JSON report.

Compared lambda={0,1,10,100}, selected on validation MAE only. Promotion within
this isolated benchmark required at least 5% lower validation MAE than the mean.
Lambda=10 selected. Validation MAE 43.65986 vs mean 63.60836. Test MAE 43.30414 vs
mean 70.17867. Test RMSE 55.40176 vs mean 80.29784. Initial regularized train
objective 14174.08491; final 1446.45597. Checkpoint reload delta=0. Reference
Ridge maximum prediction delta=0.004119. Residual heuristic interval test
coverage=0.91011; no guaranteed coverage under drift or model selection.

Result: general regression engineering acceptance met. No production TikTok
model promoted. Fixed holdout result does not establish broad model superiority.
Evidence: reports/regression_benchmark.json; core tests; benchmark command.

## E002 - Authorized connector ingestion, 2026-11-14

Real authorized Metricool settings and field discovery succeeded. An owner-brand
post query was normalized using the explicit fields contract. Private snapshots
persisted successfully; exact re-import did not add duplicate records. Real
responses did not include retention/coverage metrics. No screenshot-only historic
statistics were merged without platform IDs. Private rows, post IDs, captions and
account metrics are intentionally absent from this public ledger.

Result: manual authorized connector-to-local-database path verified. Independent
provider fetching, token transfer, OAuth and background monitoring are not claimed.

## E003 - Hook hypothesis registration, 2026-11-14

Hypothesis: first-second demonstration improves completion relative to a static
question. Independent variable: opening hook. Target: completion rate. Planned
window: 24 hours. Registered locally as observational, not randomized. No posts
published, no result observed, and no expected effect size established. Missing
retention data currently prevents outcome comparison.
