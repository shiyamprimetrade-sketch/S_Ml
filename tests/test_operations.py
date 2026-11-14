import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from fixtures import sample
from s_ml.storage import Store
from s_ml.studio import ingest_studio, studio_evidence
from s_ml.worker import add_job, claim, run_once, pause_job
from s_ml.providers import connect, health, disconnect, retry_after
from s_ml.recommendations import recommend


def evidence():
    return {'schema': 's_ml.studio-post.v1', 'source': 'tiktok_studio_owner_ui',
            'account': 'example_account', 'post_id': '123456',
            'collected_at': '2026-11-14T22:00:00+06:00', 'updated_on': '2026-11-13',
            'scope': 'post_overview_unspecified_metric_window',
            'metrics': {'views': 84, 'average_watch_time': 1.5, 'completion_rate': 0,
                        'total_watch_time': 100, 'dropoff_at': 1}}


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'db.sqlite3'
        self.inbox = self.root / 'inbox'
        self.inbox.mkdir()
        self.store = Store(self.path)
        self.store.ingest(sample())

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def publish(self, data=None, name='batch.json'):
        (self.inbox / name).write_text(json.dumps(data or sample()))

    def job(self):
        return add_job(self.store, 1, self.inbox, 30, now=100)

    def tick(self, now=100, **kwargs):
        return run_once(self.store, now=now, clock=lambda: now, **kwargs)

    def test_studio_exact_id_and_source_date(self):
        result = ingest_studio(self.store, evidence())
        self.assertTrue(result['inserted'])
        self.assertFalse(ingest_studio(self.store, evidence())['inserted'])
        data = self.store.summary()
        self.assertEqual(data['totals']['views']['observed_sum'], 84)
        self.assertIsNone(data['posts'][0]['metrics']['completion_rate']['value'])
        self.assertEqual(data['studio_evidence'][0]['metrics']['completion_rate']['value'], 0)
        self.assertEqual(data['studio_evidence'][0]['updated_on'], '2026-11-13')
        rules = recommend(data)
        self.assertIn('low_reported_completion', [rule['rule'] for rule in rules])
        self.assertNotIn('retention_missing', [rule['rule'] for rule in rules])

    def test_studio_invalid_or_unmatched_rejected(self):
        changes = [lambda d:d.update(post_id='999'), lambda d:d.update(account='other'),
                   lambda d:d.update(access_token='not-a-credential'),
                   lambda d:d['metrics'].update(completion_rate=101),
                   lambda d:d.update(collected_at='2026-11-14T20:00:00'),
                   lambda d:d.update(updated_on='2027-11-13'), lambda d:d.update(updated_on='20261113'),
                   lambda d:d.update(scope='24h')]
        for change in changes:
            data = evidence()
            change(data)
            with self.subTest(change=change), self.assertRaises(ValueError):
                ingest_studio(self.store, data)
        self.assertEqual(studio_evidence(self.store), [])

    def test_studio_backfill_and_conflict(self):
        ingest_studio(self.store, evidence())
        older = evidence()
        older.update(updated_on='2026-11-12', collected_at='2026-11-15T22:00:00+06:00')
        older['metrics']['completion_rate'] = 5
        ingest_studio(self.store, older)
        self.assertEqual(studio_evidence(self.store)[0]['metrics']['completion_rate']['value'], 0)
        conflicting = evidence()
        conflicting['metrics']['views'] = 85
        with self.assertRaises(ValueError):
            ingest_studio(self.store, conflicting)

    def test_studio_export_backup_delete(self):
        ingest_studio(self.store, evidence())
        self.assertEqual(self.store.export()['studio_observations'], [evidence()])
        backup = self.root / 'backup.db'
        self.store.backup(backup)
        with Store(backup) as copied:
            self.assertEqual(len(studio_evidence(copied)), 1)
        self.store.delete_account(1)
        self.assertEqual(studio_evidence(self.store), [])

    def test_additive_v1_migration_preserves_existing_data(self):
        self.store.close()
        with sqlite3.connect(self.path) as db:
            for name in ['studio_metrics', 'studio_batches', 'worker_receipts', 'worker_runs', 'worker_jobs', 'provider_connections']:
                db.execute('DROP TABLE '+name)
            db.execute('PRAGMA user_version=1')
        self.store = Store(self.path)
        self.assertEqual(self.store.summary()['totals']['views']['observed_sum'], 84)
        self.assertEqual(self.store.connection.execute('PRAGMA user_version').fetchone()[0], 3)

    def test_worker_idempotent_across_restarts(self):
        self.publish()
        job = self.job()
        self.assertEqual(self.tick()['processed'], 1)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.tick(131)['processed'], 0)
        self.assertEqual(self.store.summary()['batches'], 1)
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM worker_receipts WHERE job_id=?',(job,)).fetchone()[0], 1)

    def test_worker_handles_studio_and_wrong_account(self):
        self.publish(evidence(), 'studio.json')
        wrong = sample()
        wrong['account'] = 'other'
        self.publish(wrong, 'wrong.json')
        self.job()
        result = self.tick()
        self.assertEqual((result['processed'], result['rejected']), (1, 1))
        self.assertEqual(len(studio_evidence(self.store)), 1)

    def test_worker_invalid_json_isolated_and_repaired(self):
        (self.inbox / 'bad.json').write_text('{')
        self.publish()
        self.job()
        result = self.tick()
        self.assertEqual((result['processed'], result['rejected']), (1, 1))
        self.assertEqual(self.tick(131)['rejected'], 0)
        self.publish(evidence(), 'bad.json')
        self.assertEqual(self.tick(162)['processed'], 1)

    def test_worker_pause_and_resume(self):
        self.publish()
        job = self.job()
        pause_job(self.store, job)
        self.assertEqual(self.tick()['status'], 'idle')
        pause_job(self.store, job, False)
        self.assertEqual(self.tick()['processed'], 1)

    def test_exclusive_lease_and_expiry(self):
        self.job()
        self.assertIsNotNone(claim(self.store, 100, 'first'))
        with Store(self.path) as second:
            self.assertIsNone(claim(second, 101, 'second'))
            self.assertIsNotNone(claim(second, 221, 'second'))

    def test_worker_backoff_survives_restart(self):
        self.job()
        self.inbox.rmdir()
        self.assertEqual(self.tick()['status'], 'inbox_unavailable')
        row = self.store.connection.execute('SELECT * FROM worker_jobs').fetchone()
        self.assertEqual(row['failures'], 1)
        self.assertEqual(row['next_run'], 160)
        self.inbox.mkdir()
        self.publish()
        self.assertEqual(self.tick(159)['status'], 'idle')
        self.assertEqual(self.tick(160)['processed'], 1)

    def test_worker_does_not_follow_symlinks(self):
        outside = self.root / 'outside.json'
        outside.write_text(json.dumps(sample()))
        try:
            (self.inbox / 'linked.json').symlink_to(outside)
        except OSError:
            self.skipTest('Symlink support unavailable')
        self.job()
        self.assertEqual(self.tick()['processed'], 0)

    def test_worker_invalid_interval(self):
        for interval in [0, 29, float('nan'), float('inf')]:
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                add_job(self.store, 1, self.inbox, interval)

    def test_real_process_crash_replays_safely(self):
        self.publish(evidence())
        self.job()
        script = '''import os,sys
from s_ml.storage import Store
from s_ml.worker import run_once
with Store(sys.argv[1]) as store:
    run_once(store,now=100,clock=lambda:100,after_ingest=lambda:os._exit(9))
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.path)], capture_output=True)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(len(studio_evidence(self.store)), 1)
        self.assertEqual(self.tick(101)['status'], 'idle')
        self.assertEqual(self.tick(221)['processed'], 1)
        self.assertEqual(len(studio_evidence(self.store)), 1)
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM worker_receipts').fetchone()[0], 1)

    def test_missing_credentials_do_not_request_network(self):
        connect(self.store, 1, '123')
        def forbidden(*args):
            raise AssertionError('No network should run')
        result = health(self.store, 1, environment={}, send=forbidden, now=100)
        self.assertEqual(result['status'], 'credential_not_configured')
        self.assertFalse(result['live_check'])

    def test_readonly_health_and_no_secret_persistence(self):
        connect(self.store, 1, '123')
        secret = 'invented-fixture-not-an-actual-token'
        def send(url, headers):
            self.assertTrue(url.startswith('https://app.metricool.com/api/admin/simpleProfiles?'))
            self.assertEqual(headers['X-Mc-Auth'], secret)
            return 200, {}, b'{"data":[{"id":123}]}'
        result = health(self.store, 1, {'S_ML_METRICOOL_TOKEN': secret}, send, now=100)
        self.assertEqual(result['status'], 'connected')
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, '\n'.join(self.store.connection.iterdump()))

    def test_health_authorization_response_and_errors(self):
        cases = [(401, b'', 'authorization_denied'), (403, b'', 'authorization_denied'),
                 (302, b'', 'provider_unavailable'), (200, b'[]', 'brand_not_authorized'),
                 (200, b'invalid-json', 'health_check_failed')]
        for index, (code, body, expected) in enumerate(cases):
            connect(self.store, 1, '123')
            result = health(self.store, 1, {'S_ML_METRICOOL_TOKEN':'fixture'},
                            lambda u,h:(code, {}, body), now=100 + index * 100)
            self.assertEqual(result['status'], expected)

    def test_retry_after_enforced_persistently(self):
        connect(self.store, 1, '123')
        env = {'S_ML_METRICOOL_TOKEN':'fixture'}
        result = health(self.store, 1, env, lambda u,h:(429, {'Retry-After':'600'}, b''), now=100)
        self.assertEqual(result['retry_after_seconds'], 600)
        result = health(self.store, 1, env, lambda *args: self.fail('Must respect persisted rate limit'), now=200)
        self.assertEqual(result['status'], 'check_deferred')
        self.assertEqual(result['retry_after_seconds'], 500)
        self.assertEqual(retry_after({'Retry-After':'Thu, 01 Jan 1970 00:10:00 GMT'},100),500)

    def test_local_disconnect_pauses_jobs(self):
        self.job()
        connect(self.store, 1, '123')
        self.assertFalse(disconnect(self.store, 1)['provider_token_revoked'])
        self.assertEqual(health(self.store, 1)['status'], 'disconnected')
        self.assertEqual(self.tick()['status'], 'idle')

    def test_invalid_secret_reference_rejected(self):
        with self.assertRaises(ValueError):
            connect(self.store, 1, '123', 'HOME')
        with self.assertRaises(ValueError):
            connect(self.store, 1, 'not-a-user-id')
