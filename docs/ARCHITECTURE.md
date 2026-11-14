# Architecture

`ingestion.py` validates the versioned Metricool export envelope. `storage.py`
records accounts, raw batches, platform posts, immutable metric snapshots,
experiments and audit events in SQLite with foreign keys and atomic transactions.
A batch retains its provider, account, collection time and content hash. Each
metric retains its own unit and availability. Its batch identifies provenance.
Per-post latest snapshots drive totals; repeated cumulative counts are not summed.

`core.py` is the reusable numerical layer. `training.py` owns an isolated public
benchmark, candidate comparison, validation selection and test-only reporting.
Checkpoints are numeric JSON, never executable pickle. The public benchmark
artifact is not a production TikTok model. `recommendations.py` emits labelled
rules tied to available or absent evidence.

`cli.py` exposes explicit actions. `server.py` serves a read-only responsive
HTML dashboard on loopback, uses a Host allowlist, no CORS grant, no cache, no
third-party assets, and textContent for account-derived DOM content. It is not
an authenticated internet service. Browser rendering validation is still pending.

No direct dependency on other S repositories. Review of S and S-Eye README
contracts found useful patterns: project isolation, portable SQLite/JSON,
content hashes, checkpoint recovery and explicit evidence. These are reused as
patterns; no uninspected source is imported and no integration is claimed.
Future adapters should exchange versioned JSON observations and artifact hashes;
S_ML must not grant shell/UI execution just because another subsystem requests it.

Production migrations must preserve raw snapshots and user identity, add schema
migrations rather than replacing the database, and separate service secrets from
account data. The current database is schema v1; deployment is not yet supported.
