"""Durable export inbox processor. Never reads browser sessions or fetches TikTok.

Lease claims and receipts survive process restarts. Ingestion is idempotent, so a
crash after committing data but before its receipt safely replays the same input.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
from .studio import ingest_studio

MAX_BYTES = 2_000_000
MAX_FILES = 50
LEASE_SECONDS = 120


def add_job(store, account_id, inbox, interval_seconds=300, now=None):
    if not math.isfinite(interval_seconds) or not 30 <= interval_seconds <= 86400:
        raise ValueError('Local inbox interval must be between 30 seconds and one day')
    folder = Path(inbox).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError('Create the private inbox directory before registering a job')
    with store.connection:
        store.connection.execute('''INSERT INTO worker_jobs(account_id,inbox,interval_seconds,next_run)
            VALUES (?,?,?,?) ON CONFLICT(account_id,inbox) DO UPDATE SET interval_seconds=excluded.interval_seconds''',
            (account_id, str(folder), interval_seconds, time.time() if now is None else now))
    return store.connection.execute('SELECT id FROM worker_jobs WHERE account_id=? AND inbox=?',
                                    (account_id, str(folder))).fetchone()[0]


def pause_job(store, job_id, paused=True):
    # Pause prevents future claims; currently leased work checks the flag before each file.
    with store.connection:
        cursor = store.connection.execute('UPDATE worker_jobs SET paused=? WHERE id=?', (int(paused), job_id))
        if not cursor.rowcount:
            raise ValueError('Unknown worker job')


def claim(store, now, owner):
    db = store.connection
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute('''SELECT j.*,a.handle FROM worker_jobs j JOIN accounts a ON a.id=j.account_id
            WHERE paused=0 AND next_run<=? AND lease_until<=? ORDER BY next_run,id LIMIT 1''', (now, now)).fetchone()
        if row:
            db.execute('UPDATE worker_jobs SET lease_owner=?,lease_until=? WHERE id=?',
                       (owner, now + LEASE_SECONDS, row['id']))
        db.commit()
        return dict(row) if row else None
    except BaseException:
        db.rollback()
        raise


def valid_lease(store, job, owner, now):
    row = store.connection.execute('SELECT paused,lease_owner,lease_until FROM worker_jobs WHERE id=?', (job['id'],)).fetchone()
    return row is not None and not row['paused'] and row['lease_owner'] == owner and row['lease_until'] > now


def run_once(store, now=None, clock=time.time, owner=None, after_ingest=None):
    now = clock() if now is None else now
    owner = owner or uuid.uuid4().hex
    job = claim(store, now, owner)
    if job is None:
        return {'status': 'idle', 'processed': 0, 'rejected': 0}
    processed = rejected = 0
    status = 'ok'
    try:
        inbox = Path(job['inbox'])
        if not inbox.is_dir():
            raise OSError('Inbox unavailable')
        # Only consume explicitly published .json files; producers use atomic rename.
        candidates = sorted(inbox.glob('*.json'))
        examined = 0
        for path in candidates:
            tick = clock()
            if not valid_lease(store, job, owner, tick):
                status = 'interrupted'
                break
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > MAX_BYTES:
                # Do not read oversized files or expose filenames in audit/status.
                continue
            raw = path.read_bytes()
            if len(raw) > MAX_BYTES:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if store.connection.execute('SELECT 1 FROM worker_receipts WHERE job_id=? AND digest=?', (job['id'], digest)).fetchone():
                continue
            if examined >= MAX_FILES:
                break
            examined += 1
            code, outcome = 'ok', 'processed'
            try:
                data = json.loads(raw)
                if not isinstance(data, dict) or data.get('account') != job['handle']:
                    raise ValueError('Account mismatch')
                if data.get('schema') == 's_ml.metricool-export.v1':
                    account = store.connection.execute('SELECT brand_id FROM accounts WHERE id=?', (job['account_id'],)).fetchone()
                    if data.get('brand_id') != account[0]:
                        raise ValueError('Brand mismatch')
                    store.ingest(data)
                elif data.get('schema') == 's_ml.studio-post.v1':
                    ingest_studio(store, data)
                else:
                    raise ValueError('Unsupported schema')
            except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
                code, outcome = 'invalid_export', 'rejected'
                rejected += 1
            else:
                processed += 1
                if after_ingest:
                    after_ingest()  # Fault injection hook; no receipt if a process dies here.
            with store.connection:
                store.connection.execute('INSERT INTO worker_receipts VALUES (?,?,?,?,?)',
                                          (job['id'], digest, outcome, code, clock()))
                store.connection.execute('UPDATE worker_jobs SET lease_until=? WHERE id=? AND lease_owner=?',
                                          (clock() + LEASE_SECONDS, job['id'], owner))
    except OSError:
        status = 'inbox_unavailable'
    except Exception:
        # No filenames, response bodies, captions or credential values in operational errors.
        status = 'processing_error'
    finally:
        end = clock()
        failures = job['failures'] + 1 if status in ('inbox_unavailable', 'processing_error') else 0
        delay = min(86400, job['interval_seconds'] * 2 ** min(failures, 8))
        with store.connection:
            # A stale owner must never clear a successor's lease.
            cursor = store.connection.execute('''UPDATE worker_jobs SET next_run=?,last_run=?,last_status=?,
                failures=?,lease_owner=NULL,lease_until=0 WHERE id=? AND lease_owner=?''',
                (end + delay, end, status, failures, job['id'], owner))
            if cursor.rowcount:
                store.connection.execute('INSERT INTO worker_runs(job_id,at,status,processed,rejected) VALUES (?,?,?,?,?)',
                                          (job['id'], end, status, processed, rejected))
    return {'job_id': job['id'], 'status': status, 'processed': processed, 'rejected': rejected}


def run_forever(database, stop=None):
    from .storage import Store
    from threading import Event
    stop = stop or Event()
    while not stop.is_set():
        with Store(database) as store:
            result = run_once(store)
        if result['status'] == 'idle':
            stop.wait(1)
