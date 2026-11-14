# S_ML

S_ML is a local-first machine-learning and observation engine. Its first mission
is authorized TikTok analytics. Version 0.1.0 is an **engineering foundation**,
not a completed autonomous TikTok forecasting service.

## Working now

- NumPy regression trained by explicit batch or mini-batch gradient descent,
  L2 regularization, training-only scaling and JSON save/reload.
- Public real-data regression benchmark against a mean baseline and scikit-learn
  Ridge, validation-only model selection, held-out test errors and learning curves.
- Diagonal Gaussian anomaly scores (no calibrated alert threshold yet).
- Authorized Metricool connector export import, strict schema validation,
  platform-ID reconciliation, immutable SQLite metric snapshots and audit records.
- Missing values, units and timestamps remain explicit; backfills do not overwrite
  newer metadata. Exports, backups, account deletion and experiment registration.
- Read-only local dashboard and CLI. Diagnostics are labelled fixed rules.

## Install and verify

Python 3.11 or newer:

```bash
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead: .\.venv\Scripts\Activate.ps1
python -m pip install .
python -m unittest discover -s tests -v
python -m s_ml benchmark
python -m s_ml status
python -m s_ml serve
```

Open http://127.0.0.1:8766 on the computer running S_ML. The dashboard reads local
records; it does not fetch the platform when refreshed. `requirements.lock`
records the verified Python 3.12 scientific dependency versions. Other supported
Python versions use the compatible dependency bounds in `pyproject.toml`.

## Authorized ingestion

An authorized ChatGPT Metricool connector call can produce the rows consumed by
S_ML. It is **not** a transferable OAuth grant or an application access token.
See [the exact import contract](docs/PROVIDERS.md). Store your own export under
`private/`; that directory and `runtime/` are ignored and must stay out of Git.

```bash
python -m s_ml import-metricool private/metricool_snapshot.json
python -m s_ml status
python -m s_ml recommend
python -m s_ml export private/account_export.json
python -m s_ml backup private/account_backup.sqlite3
python -m s_ml experiment --account-id 1 --hypothesis "Result-first hook improves completion" --variable "opening hook" --metric completion_rate --hours 24
python -m s_ml delete-account 1 --confirm
```

There are no credentials in the repository. No plaintext token store is provided.
The local SQLite database and exports contain private account data, are not
encrypted by this application, and need operating-system access protection.
Deletion clears the local account records; separately created exports/backups
need separate deletion. The CLI does not revoke provider grants.

## Evidence and continuation

- [Current checkpoint](docs/STATUS.md)
- [Lecture-to-code mapping](docs/STANFORD_LEARNING_IMPLEMENTATION.md)
- [Public benchmark results](reports/regression_benchmark.json)
- [Roadmap](docs/ROADMAP.md)

The source repo was empty at audit. No existing implementation was replaced.
No TikTok horizon forecasts are trained: snapshots at different post ages are
not comparable outcome labels. Independent monitoring, full OAuth lifecycle,
classification, trees, neural networks, clustering, drift, deployment, and
production release acceptance remain future milestones.
