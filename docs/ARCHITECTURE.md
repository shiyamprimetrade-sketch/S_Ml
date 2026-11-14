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
account data. The current database is schema v3, migrated additively from v1/v2; deployment is not yet supported.

Version 0.2 adds `studio.py` for separately sourced owner-visible observations;
`worker.py` for a durable local inbox queue; and `providers.py` for connection
metadata plus fixed-origin read-only API health. `migrations.py` adds schema v2
without replacing v1 snapshots. Studio rows reconcile by existing account/post
IDs; they do not double-count account totals. Worker receipts and leases are
persisted, and expired lease owners cannot clear a successor's claim.


Version 0.3 adds `promotion.py`: numeric checkpoint snapshots, a per-mission
active-model pointer, held-out decision ledger, consumed evaluation IDs and
explicit rollback. Temporal guards use both forecast origin and outcome
availability. Promotion decisions and pointer changes are one SQLite transaction.
A trained candidate remains inactive unless the gate passes; prediction adapters
must resolve the active pointer. Account-linked registry records cascade on
account deletion. The public benchmark does not alter this registry.
