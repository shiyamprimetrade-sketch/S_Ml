"""Fixed diagnostics are labelled rules, never passed off as a trained model."""

def recommend(summary):
    posts = summary["posts"]
    output = [{"kind": "diagnostic_rule", "rule": "collect_matched_horizons",
               "evidence": {"observed_posts": len(posts)},
               "recommendation": "Collect post snapshots near 1h, 24h and 7d before comparing outcomes.",
               "confidence": "high for data requirement; no quantified performance benefit",
               "alternatives": ["Post age and platform distribution differ"],
               "test": "Compare posts using the same elapsed-time window"}]
    studio = summary.get('studio_evidence', [])
    retention = {(item['account_id'], item['post_id']): item for item in studio
                 if item['metrics'].get('completion_rate', {}).get('value') is not None}
    for item in retention.values():
        rate = item['metrics']['completion_rate']['value']
        if rate < 10:
            output.append({'kind': 'diagnostic_rule', 'rule': 'low_reported_completion',
                           'evidence': {'post_id': item['post_id'], 'completion_rate_percent': rate,
                                        'source': item['source'], 'updated_on': item['updated_on'],
                                        'metric_window': item['scope']},
                           'recommendation': 'Test showing the result in the first second; compare completion at matched post ages.',
                           'confidence': 'hypothesis only; small observational sample',
                           'alternatives': ['Audience mismatch', 'Duration or distribution differences', 'Delayed reporting'],
                           'expected_effect': None, 'test': 'Register a matched-window opening-hook comparison'})
    missing = [p["post_id"] for p in posts if p["metrics"]["completion_rate"]["value"] is None and (p['account_id'],p['post_id']) not in retention]
    if missing:
        output.append({"kind": "diagnostic_rule", "rule": "retention_missing", "evidence": {"post_ids": missing},
                       "recommendation": "Import authorized retention measurements before diagnosing early drop-off.",
                       "confidence": "high: unavailable fields", "expected_effect": None,
                       "alternatives": ["Provider scope or data freshness may limit retention fields"],
                       "test": "Re-fetch or import an owner-exported retention report with platform IDs"})
    return output
