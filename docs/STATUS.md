# Durable checkpoint

Date: 2026-11-14 (Asia/Dhaka).
Version: 0.2.0 engineering milestone; full mission is not complete.
Branch: `feature/verified-ml-foundation`, existing PR #1.
Previous commit: `b5b626dfb41ef736733da60b4985376ab0da2c4f`.
Resolve branch HEAD/PR for the latest commit; a file cannot embed its own hash.

## Completed now

- Preserved regression core, public benchmark, numeric checkpoints and all prior observations.
- Added additive SQLite v1 -> v2 migration and distinct owner-visible Studio post evidence.
- Reconciled Studio observations by verified account/platform IDs. Provider update day,
  collection timestamp and unknown metric windows remain distinct. Source totals are not summed.
- Added durable local export-inbox jobs, exclusive expiring leases, receipts,
  bounded batches, invalid-input isolation, retry backoff, pause/resume and status.
- Verified replay after an actual separate-process crash between data commit and receipt.
- Added environment-secret references and fixed-origin read-only Metricool health,
  sanitized errors, no redirects, persisted Retry-After and local disconnect/pause.
- Added Studio evidence and import-worker health to the read-only dashboard.
- Refreshed the real authorized connector export and stored owner Studio evidence privately.
- The authorized Cloud Browser is signed in and left open on owner analytics. Session
  persistence depends on the browser/provider; no credentials/cookies were exported to S_ML.

## Verification

47 local tests pass. Coverage includes all previous ML/ingestion checks plus
source date precision, exact post association, additive migration, separate totals,
worker idempotence, pause/resume, exclusive leases, actual process-crash recovery,
missing credentials, response errors, secret non-persistence and retry deferral.
Version 0.2.0 wheel builds and its package contents exclude private/runtime data.
See current PR checks for CI; never infer passing CI from configuration alone.

Public regression benchmark remains unchanged: test MAE 43.30414 vs mean baseline
70.17867; checkpoint restore delta 0. No TikTok model or forecast promoted.
Previous foundation commit passed Python 3.11/3.12/3.13 and dependency-audit jobs:
https://github.com/shiyamprimetrade-sketch/S_Ml/actions/runs/43587860448 .

## Actual access and remaining gaps

Existing authorized Metricool connector and owner browser inspection work during
this session. Repeated connector measurements were unchanged; tool retrieval time
does not prove fresh platform metrics. Studio provided previous-day update labels.
Private account observations, exports, inbox files and SQLite data remain ignored
by Git. Do not commit them to make continuation convenient.

Standalone connection health correctly reports credential_not_configured. No API
token, API plan eligibility, scope enumeration, OAuth flow, API analytics fetch,
remote revocation, or always-on deployment has been verified. The new worker scans
a local export inbox; it does not obtain new platform observations independently.
A configured job is not evidence of a continuously running worker process.

HTTP dashboard tests pass; browser rendering QA remains pending because the local
Chromium process could not launch in this environment. Supplied lecture state is
unchanged: Lecture2 and Lectures10-18 inspected; Lecture1 absent.

## Next task

Implement the standalone read-only analytics adapter from an official documented
response schema, then horizon-label readiness and provider-freshness checks. Finish
transport/schema tests before asking for any separate app credentials. Do not copy
browser sessions into the application. Preserve PR #1 and all v1/v2 database data.

Pending later: full OAuth lifecycle, deployed platform collection, evaluated TikTok
forecasts, additional course algorithms, learned content generation, experimental
outcomes, production access controls, and complete production release acceptance.
