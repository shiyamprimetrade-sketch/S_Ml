"""Owner-visible Studio evidence, kept distinct from connector lifetime snapshots."""
from datetime import date
import hashlib
import json
import re
from .ingestion import aware_time, number

UNITS = {'views': 'count', 'likes': 'count', 'comments': 'count', 'shares': 'count',
         'saves': 'count', 'total_watch_time': 'seconds', 'average_watch_time': 'seconds',
         'completion_rate': 'percent', 'new_followers': 'count', 'dropoff_at': 'seconds'}


def validate_studio(data):
    allowed = {'schema', 'source', 'account', 'post_id', 'collected_at', 'updated_on', 'scope', 'metrics'}
    if not isinstance(data, dict) or set(data) != allowed:
        raise ValueError('Studio observation must contain exactly the documented fields')
    if data['schema'] != 's_ml.studio-post.v1' or data['source'] != 'tiktok_studio_owner_ui':
        raise ValueError('Unsupported Studio observation provenance')
    if not isinstance(data['account'], str) or not re.fullmatch(r'[\w.]{1,64}', data['account'], re.ASCII):
        raise ValueError('Invalid account handle')
    if not isinstance(data['post_id'], str) or not re.fullmatch(r'\d{1,30}', data['post_id']):
        raise ValueError('Invalid platform post ID')
    collected = aware_time(data['collected_at'])
    updated = date.fromisoformat(data['updated_on'])
    if updated.isoformat() != data['updated_on']:
        raise ValueError('Provider update date must use YYYY-MM-DD')
    # updated_on has day precision and an unknown provider timezone.
    # Allow one-day calendar offset; never manufacture a midnight update instant.
    if (updated - collected.date()).days > 1:
        raise ValueError('Provider update day cannot be in the future')
    if data['scope'] != 'post_overview_unspecified_metric_window':
        raise ValueError('Metric window must remain explicit; do not invent a forecast horizon')
    if not isinstance(data['metrics'], dict) or set(data['metrics']) - set(UNITS):
        raise ValueError('Unknown Studio metric')
    if not data['metrics']:
        raise ValueError('At least one metric is required')
    metrics = {}
    for name, value in data['metrics'].items():
        unit = UNITS[name]
        numeric = number(value, unit)
        metrics[name] = {'value': numeric, 'unit': unit,
                         'availability': 'unavailable' if numeric is None else 'observed'}
    payload = json.dumps(data, sort_keys=True, allow_nan=False)
    return collected.isoformat(), metrics, payload, hashlib.sha256(payload.encode()).hexdigest()


def ingest_studio(store, data):
    collected, metrics, payload, digest = validate_studio(data)
    db = store.connection
    # Exact account + platform ID association; captions and similar values never match posts.
    matches = db.execute('''SELECT p.account_id FROM posts p JOIN accounts a ON a.id=p.account_id
        WHERE a.handle=? AND p.post_id=?''', (data['account'], data['post_id'])).fetchall()
    if len(matches) != 1:
        raise ValueError('Studio post must match exactly one previously imported account/post ID')
    aid = matches[0][0]
    with db:
        prior = db.execute('''SELECT digest FROM studio_batches
            WHERE account_id=? AND post_id=? AND collected_at=?''', (aid, data['post_id'], collected)).fetchone()
        if prior:
            if prior[0] != digest:
                raise ValueError('Conflicting Studio observation at this timestamp')
            return {'inserted': False, 'observations': 1, 'digest': digest}
        cursor = db.execute('''INSERT INTO studio_batches
            (account_id,post_id,collected_at,updated_on,scope,digest,payload) VALUES (?,?,?,?,?,?,?)''',
            (aid, data['post_id'], collected, data['updated_on'], data['scope'], digest, payload))
        for name, metric in metrics.items():
            db.execute('INSERT INTO studio_metrics VALUES (?,?,?,?,?)',
                       (cursor.lastrowid, name, metric['value'], metric['unit'], metric['availability']))
    return {'inserted': True, 'observations': 1, 'digest': digest}


def studio_evidence(store):
    rows = store.connection.execute('''SELECT b.*,a.handle FROM studio_batches b
        JOIN accounts a ON a.id=b.account_id ORDER BY updated_on DESC,collected_at DESC,id DESC''')
    result, seen = [], set()
    for row in rows:
        key = (row['account_id'], row['post_id'])
        if key in seen:
            continue
        seen.add(key)
        result.append({'account_id': row['account_id'], 'account': row['handle'], 'post_id': row['post_id'],
                       'source': 'tiktok_studio_owner_ui', 'collected_at': row['collected_at'],
                       'updated_on': row['updated_on'], 'update_precision': 'day; timezone unspecified',
                       'scope': row['scope'],
                       'metrics': {m['name']: {'value': m['value'], 'unit': m['unit'], 'availability': m['availability']}
                                   for m in store.connection.execute('SELECT * FROM studio_metrics WHERE batch_id=?', (row['id'],))}})
    return result
