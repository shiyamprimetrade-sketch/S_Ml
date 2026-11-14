"""Fixed diagnostics are labelled rules, never passed off as a trained model."""

def recommend(summary):
    posts = summary["posts"]
    output = [{"kind": "diagnostic_rule", "rule": "collect_matched_horizons",
               "evidence": {"observed_posts": len(posts)},
               "recommendation": "Collect post snapshots near 1h, 24h and 7d before comparing outcomes.",
               "confidence": "high for data requirement; no quantified performance benefit",
               "alternatives": ["Post age and platform distribution differ"],
               "test": "Compare posts using the same elapsed-time window"}]
    missing = [p["post_id"] for p in posts if p["metrics"]["completion_rate"]["value"] is None]
    if missing:
        output.append({"kind": "diagnostic_rule", "rule": "retention_missing", "evidence": {"post_ids": missing},
                       "recommendation": "Import authorized retention measurements before diagnosing early drop-off.",
                       "confidence": "high: unavailable fields", "expected_effect": None,
                       "alternatives": ["Provider scope or data freshness may limit retention fields"],
                       "test": "Re-fetch or import an owner-exported retention report with platform IDs"})
    return output
