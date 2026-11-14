# Provider contracts and authorization status

## Working path: existing authorized Metricool connector

Use the connector's brand settings to verify identity/timezone. Discover TikTok
post fields rather than guessing them. Request these fields in this exact order:

```json
["TKPO02","TKPO03","TKPO05","TKPO06","TKPO07","TKPO08","TKPO09","TKPO10","TKPO11","TKPO13","TKPO14","TKPO15","TKPO22"]
```

Wrap the returned `rows` in the following private JSON envelope, replacing the
example identity and timestamp with actual verified retrieval metadata:

```json
{
  "schema": "s_ml.metricool-export.v1",
  "source": "metricool_authorized_connector",
  "account": "example_account",
  "brand_id": "123",
  "timezone": "Asia/Dhaka",
  "observed_at": "2026-11-14T20:00:00+06:00",
  "fields": ["TKPO02","TKPO03","TKPO05","TKPO06","TKPO07","TKPO08","TKPO09","TKPO10","TKPO11","TKPO13","TKPO14","TKPO15","TKPO22"],
  "rows": []
}
```

This is an export bridge, not an embedded ChatGPT connector or automatic fetch
inside the installed Python application. Provenance labels are supplied by the
operator and not cryptographic proof of consent. Import only exports obtained
through authorized access. Post IDs are extracted from official URLs, captions
are not used to match historical screenshots, and unmatched old observations are
excluded. Missing values are null. PHOTO duration zero is not a video duration.

TKPO02's naive timestamp is explicitly interpreted in the verified brand
 timezone. Provider timestamp interpretation still needs an independent platform
cross-check before exact 1-hour targets. Collection timestamp does not establish
platform data freshness. Completion field TKPO13 is documented as a percentage;
provider scale must be verified with an actual non-null response before model use.

## Independent app authorization: not implemented

Metricool's official documentation distinguishes MCP access from API access.
Direct API requests require a separate token in `X-Mc-Auth` plus userId/blogId.
The ChatGPT connector's token is never copied, retrieved or committed. A future
standalone adapter must inspect available scope/plan support, use encrypted
secret storage or external secrets, and implement disconnect/revocation semantics.
No separate credential is needed for the already verified manual export path.

Official references read on 2026-11-14:

- https://help.metricool.com/basic-guide-for-api-integration-r97af
- https://help.metricool.com/mcp-vs-api-access-what-is-the-difference-5y3ib
- https://developers.tiktok.com/doc/tiktok-api-v2-video-query

TikTok's official video query endpoint verifies authorized-user ownership,
accepts up to 20 video IDs and requires `video.list`. Its documented video fields
include views, likes, comments and shares; watch-time/completion are not fields
in that endpoint. Do not claim that obtaining Login Kit or Display API access
grants all TikTok Studio analytics. TikTok developer registration, reviewed app
configuration and supported authorization are separate from the Metricool grant.
Version 0.2 adds a fixed-origin read-only standalone Metricool health check using
an environment-secret reference. It has transport tests but no configured live API
credential. Full OAuth connect/refresh/revoke/account switching and direct analytics
fetch remain unimplemented. See OPERATIONS.md.
