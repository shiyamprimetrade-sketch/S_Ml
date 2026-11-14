"""Additive v1 -> v2 migration. Existing raw observations and checkpoints survive."""
MIGRATION_2 = '''
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS studio_batches (
 id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 post_id TEXT NOT NULL, collected_at TEXT NOT NULL, updated_on TEXT NOT NULL,
 scope TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(account_id,post_id,collected_at), UNIQUE(account_id,digest),
 FOREIGN KEY(account_id,post_id) REFERENCES posts(account_id,post_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS studio_metrics (
 batch_id INTEGER NOT NULL REFERENCES studio_batches(id) ON DELETE CASCADE,
 name TEXT NOT NULL,value REAL,unit TEXT NOT NULL,availability TEXT NOT NULL,
 PRIMARY KEY(batch_id,name));
CREATE TABLE IF NOT EXISTS worker_jobs (
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 inbox TEXT NOT NULL,interval_seconds REAL NOT NULL,next_run REAL NOT NULL,paused INTEGER NOT NULL DEFAULT 0,
 lease_owner TEXT,lease_until REAL NOT NULL DEFAULT 0,failures INTEGER NOT NULL DEFAULT 0,
 last_run REAL,last_status TEXT NOT NULL DEFAULT 'never_run', UNIQUE(account_id,inbox));
CREATE TABLE IF NOT EXISTS worker_receipts (
 job_id INTEGER NOT NULL REFERENCES worker_jobs(id) ON DELETE CASCADE,
 digest TEXT NOT NULL,outcome TEXT NOT NULL,code TEXT NOT NULL,at REAL NOT NULL,
 PRIMARY KEY(job_id,digest));
CREATE TABLE IF NOT EXISTS worker_runs (
 id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES worker_jobs(id) ON DELETE CASCADE,
 at REAL NOT NULL,status TEXT NOT NULL,processed INTEGER NOT NULL,rejected INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS provider_connections (
 account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL,token_environment TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
 last_check REAL,last_status TEXT NOT NULL DEFAULT 'not_checked',next_check REAL NOT NULL DEFAULT 0);
PRAGMA user_version=2;
COMMIT;
'''
