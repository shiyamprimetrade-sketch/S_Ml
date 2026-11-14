import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from fixtures import sample
from s_ml.ingestion import parse_export
from s_ml.storage import Store
from s_ml.recommendations import recommend


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'data.sqlite3'
        self.store = Store(self.path)
        self.data = sample()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_missing_and_zero(self):
        p = parse_export(self.data)[0]
        self.assertEqual(p.metrics['comments']['value'], 0)
        self.assertIsNone(p.metrics['completion_rate']['value'])
        self.assertEqual(p.metrics['completion_rate']['availability'], 'unavailable')

    def test_photo_duration(self):
        self.data['rows'][0][-1] = 'PHOTO'
        self.assertEqual(parse_export(self.data)[0].metrics['duration']['availability'], 'not_applicable')

    def test_explicit_field_order(self):
        self.data['fields'].reverse()
        self.data['rows'][0].reverse()
        self.assertEqual(parse_export(self.data)[0].post_id, '123456')

    def test_persistent_deduplication(self):
        self.assertTrue(self.store.ingest(self.data)['inserted'])
        self.assertFalse(self.store.ingest(self.data)['inserted'])
        with Store(self.path) as reopened:
            result = reopened.summary()
            self.assertEqual(result['batches'], 1)
            self.assertEqual(result['totals']['views']['observed_sum'], 84)
            self.assertEqual(len(result['posts']), 1)

    def test_snapshot_totals(self):
        self.store.ingest(self.data)
        self.data['observed_at'] = '2026-11-15T20:00:00+06:00'
        self.data['rows'][0][4] = '90'
        self.store.ingest(self.data)
        result = self.store.summary()
        self.assertEqual(result['batches'], 2)
        self.assertEqual(result['totals']['views']['observed_sum'], 90)

    def test_backfill_does_not_replace_latest(self):
        self.store.ingest(self.data)
        self.data['observed_at'] = '2026-11-14T19:00:00+06:00'
        self.data['rows'][0][4] = '70'
        self.data['rows'][0][2] = 'old'
        self.store.ingest(self.data)
        result = self.store.summary()
        self.assertEqual(result['totals']['views']['observed_sum'], 84)
        self.assertNotEqual(result['posts'][0]['caption'], 'old')

    def test_conflicting_snapshot(self):
        self.store.ingest(self.data)
        self.data['rows'][0][4] = '999'
        with self.assertRaises(ValueError):
            self.store.ingest(self.data)
        self.assertEqual(self.store.summary()['totals']['views']['observed_sum'], 84)

    def test_atomic_bad_batch(self):
        bad = copy.deepcopy(self.data['rows'][0])
        bad[1] = 'https://www.tiktok.com/@example_account/video/999'
        bad[4] = '-4'
        self.data['rows'].append(bad)
        with self.assertRaises(ValueError):
            self.store.ingest(self.data)
        self.assertEqual(self.store.summary()['accounts'], [])

    def test_invalid_exports(self):
        changes = [lambda d: d.update(observed_at='2026-11-14T20:00:00'), lambda d: d['fields'].pop(),
                   lambda d: d['rows'][0].__setitem__(4, 'NaN'), lambda d: d['rows'][0].__setitem__(4, '1.5'),
                   lambda d: d['rows'][0].__setitem__(9, '101'),
                   lambda d: d['rows'][0].__setitem__(1, 'https://evil.test/@example_account/video/123456'),
                   lambda d: d.update(account='other'), lambda d: d['rows'].append(d['rows'][0]),
                   lambda d: d['rows'][0].__setitem__(0, '20261116180000')]
        for change in changes:
            data = copy.deepcopy(self.data)
            change(data)
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_export(data)

    def test_backup_export_delete(self):
        self.assertIsNone(self.store.summary()['totals']['views']['observed_sum'])
        self.store.ingest(self.data)
        self.assertEqual(self.store.export()['batches'][0], self.data)
        backup = Path(self.temp.name) / 'backup.db'
        self.store.backup(backup)
        with Store(backup) as copied:
            self.assertEqual(copied.summary()['totals']['views']['observed_sum'], 84)
        self.store.delete_account(1)
        self.assertEqual(self.store.export()['batches'], [])
        self.assertEqual(self.store.summary()['posts'], [])

    def test_diagnostics_freshness(self):
        self.store.ingest(self.data)
        result = self.store.summary(now=datetime(2026, 11, 14, 15, tzinfo=timezone.utc))
        self.assertEqual(result['freshness_seconds'], 3600)
        rules = recommend(result)
        self.assertTrue(all(r['kind'] == 'diagnostic_rule' for r in rules))
        self.assertEqual(rules[1]['evidence']['post_ids'], ['123456'])

    def test_experiments(self):
        self.store.ingest(self.data)
        self.assertEqual(self.store.experiment(1, 'Result-first hook improves retention', 'hook', 'views', 24), 1)
        for hypothesis, hours in [('', 24), ('x', float('nan'))]:
            with self.assertRaises(ValueError):
                self.store.experiment(1, hypothesis, 'hook', 'views', hours)

    def test_credentials_rejected_before_persistence(self):
        self.data['access_token'] = 'synthetic-not-a-real-credential'
        with self.assertRaises(ValueError):
            self.store.ingest(self.data)
        self.assertEqual(self.store.export()['batches'], [])

    def test_newer_database_schema_not_overwritten(self):
        import sqlite3
        path = Path(self.temp.name) / 'future.db'
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA user_version=2')
        with self.assertRaises(ValueError):
            Store(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
