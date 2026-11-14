# Version 0.2: durable observation processing

## Keep the three access surfaces separate

1. The user-controlled Cloud Browser can remain signed in to TikTok while its
   session remains valid. Owner-visible Studio data can then be inspected during
   a conversation. No browser cookies, passwords or verification codes are read
   into S_ML or copied to GitHub. A browser login is not application OAuth.
2. The existing authorized Metricool connector can produce fresh exports. Its
   collection timestamp does not establish provider freshness; unchanged rows
   can remain stale even if the tool call succeeds.
3. Standalone S_ML can process owner-authorized exports and optionally check a
   separately configured Metricool API connection. No direct analytics fetcher or
   full OAuth lifecycle is implemented yet. No unattended platform collection is
   deployed by this milestone.

## Studio evidence contract

`python -m s_ml import-studio private/studio-post.json` accepts this structure:

```json
{
  "schema": "s_ml.studio-post.v1",
  "source": "tiktok_studio_owner_ui",
  "account": "example_account",
  "post_id": "123456",
  "collected_at": "2026-11-14T22:00:00+06:00",
  "updated_on": "2026-11-13",
  "scope": "post_overview_unspecified_metric_window",
  "metrics": {
    "views": 84,
    "average_watch_time": 1.5,
    "completion_rate": 0,
    "total_watch_time": 100,
    "dropoff_at": 1
  }
}
```

This is invented example data, not an account observation. Supported fields are
listed in `studio.UNITS`. Zero remains observed; null remains unavailable. The
account and exact platform post ID must already match one imported connector
post. Unmatched screenshots or similar captions do not establish identity.

`updated_on` preserves the provider's day precision and unknown timezone. It is
not converted into an invented update instant. The interface's metric window is
not assumed to be lifetime or a 24-hour forecast target. Studio evidence is shown
separately from connector snapshots and never added to connector view totals.
Latest evidence is selected by provider update day, then collection time. An
older-day backfill cannot displace a newer source day just because it was collected
later. Retain independently reported averages; do not recompute watch time from
other counters unless their definitions/windows are verified.

## Durable local worker

Create a private inbox, then register it against the imported account ID:

```bash
mkdir -p private/inbox
python -m s_ml worker-add --account-id 1 --inbox private/inbox --interval 300
python -m s_ml worker-once
python -m s_ml worker-run
```

On Windows, create the directory using File Explorer or `New-Item -ItemType
Directory -Force private/inbox`. The worker command is otherwise the same.

Producers must write a temporary file and atomically rename it to `.json` once
complete. Supported inputs are the versioned Metricool export or Studio post
contract. The worker never fetches TikTok or Metricool by itself. Its interval is
an inbox scan interval, not a promise about platform freshness.

SQLite stores due times, exclusive leases, receipts, run outcomes and failures.
A crashed owner loses its lease after 120 seconds. If data was committed just
before the crash, replay is safe because ingestion itself is idempotent. The
process-crash test uses a separate Python process terminated immediately after
commit, then verifies recovery without duplicate observations.

Malformed inputs are recorded as rejected by content hash; corrected bytes can
be processed on a later scan. Payloads and filenames do not enter error logs.
Other valid files continue processing. Each cycle consumes at most 50 unseen
eligible files; symlinks, temporary files and files over 2 MB are skipped. An
unavailable inbox triggers exponential retry delay (bounded at one day).

```bash
python -m s_ml worker-pause 1
python -m s_ml worker-pause 1 --resume
python -m s_ml status
```

Pause blocks subsequent claims and the next file boundary of a running cycle.
It does not roll back an already committed observation. OS process/service
supervision is still required for a worker to run when a terminal or conversation
closes. This repository does not claim that such a host was deployed.

## Separate API connection health

Register the numeric Metricool user ID and an environment-secret reference:

```bash
python -m s_ml connection-add --account-id 1 --user-id YOUR_NUMERIC_USER_ID --token-environment S_ML_METRICOOL_TOKEN
python -m s_ml connection-health 1
python -m s_ml connection-disconnect 1
```

Configure the token only in the chosen host's secret manager/environment. Do not
put it in command arguments, the repository, account exports or chat. With no
credential configured, health returns `credential_not_configured` without a
network request. Registering metadata does not authorize an application.

Health makes one GET to the documented, fixed HTTPS simpleProfiles endpoint;
redirects are refused so credentials are not forwarded. Results distinguish
connected, denied, missing brand, rate limited and unavailable. Retry-After is
persisted, and repeat health requests wait until it expires. Token permission
scopes are not exposed by this endpoint and are labelled unknown. Health testing
used simulated transport; no separate API credential was available for a live
standalone health test.

Local disconnect disables the configured reference and pauses account jobs. It
**does not revoke the remote token** or delete the environment secret. Remote
revocation/rotation remains an explicit provider-side action. Read-only browser
inspection, import jobs and API token references have independent lifecycles.

Official authentication/health reference read 2026-11-14:
https://help.metricool.com/basic-guide-for-api-integration-r97af . It documents
`X-Mc-Auth`, userId/blogId and the simpleProfiles endpoint. Direct API access
requires an eligible Metricool plan and a separate token; connector access does
not prove plan eligibility. No paid plan is assumed or purchased.
