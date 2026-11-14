"""SQLite snapshots with source/time/unit/missingness, atomic ingestion and export."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from .ingestion import parse_export, aware_time

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, provider TEXT NOT NULL, brand_id TEXT NOT NULL, handle TEXT NOT NULL,
 UNIQUE(provider,brand_id,handle));
CREATE TABLE IF NOT EXISTS batches (
 id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 observed_at TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(account_id,observed_at), UNIQUE(account_id,digest));
CREATE TABLE IF NOT EXISTS posts (
 account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 post_id TEXT NOT NULL, published_at TEXT NOT NULL, caption TEXT NOT NULL, content_type TEXT NOT NULL,
 metadata_at TEXT NOT NULL, PRIMARY KEY(account_id,post_id));
CREATE TABLE IF NOT EXISTS metrics (
 batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
 account_id INTEGER NOT NULL, post_id TEXT NOT NULL, name TEXT NOT NULL,
 value REAL, unit TEXT NOT NULL, availability TEXT NOT NULL,
 PRIMARY KEY(batch_id,post_id,name),
 FOREIGN KEY(account_id,post_id) REFERENCES posts(account_id,post_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, event TEXT NOT NULL, at TEXT NOT NULL, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments (
 id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, hypothesis TEXT NOT NULL, variable TEXT NOT NULL,
 target_metric TEXT NOT NULL, observation_hours REAL NOT NULL, design TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'planned');
PRAGMA user_version=1;
"""


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise ValueError("Unsupported database version; explicit migration required")
        self.connection.executescript(SCHEMA)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def ingest(self, data):
        posts = parse_export(data)  # Validate the entire batch before any mutation.
        observed = aware_time(data["observed_at"]).isoformat()
        payload = json.dumps(data, sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        db = self.connection
        with db:
            db.execute("INSERT OR IGNORE INTO accounts(provider,brand_id,handle) VALUES (?,?,?)",
                       (data["source"], data["brand_id"], data["account"]))
            aid = db.execute("SELECT id FROM accounts WHERE provider=? AND brand_id=? AND handle=?",
                             (data["source"], data["brand_id"], data["account"])).fetchone()[0]
            existing = db.execute("SELECT digest FROM batches WHERE account_id=? AND observed_at=?", (aid, observed)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError("Conflicting payload for existing observation timestamp")
                return {"inserted": False, "posts": len(posts), "digest": digest}
            cursor = db.execute("INSERT INTO batches(account_id,observed_at,digest,payload) VALUES (?,?,?,?)",
                                (aid, observed, digest, payload))
            batch_id = cursor.lastrowid
            for post in posts:
                prior = db.execute("SELECT published_at FROM posts WHERE account_id=? AND post_id=?", (aid, post.post_id)).fetchone()
                if prior and prior[0] != post.published_at:
                    raise ValueError("Publication timestamp changed for same platform post ID")
                db.execute("""INSERT INTO posts VALUES (?,?,?,?,?,?)
                    ON CONFLICT(account_id,post_id) DO UPDATE SET
                    caption=excluded.caption,content_type=excluded.content_type,metadata_at=excluded.metadata_at
                    WHERE excluded.metadata_at > posts.metadata_at""",
                    (aid, post.post_id, post.published_at, post.caption, post.content_type, observed))
                for name, metric in post.metrics.items():
                    db.execute("INSERT INTO metrics VALUES (?,?,?,?,?,?,?)",
                               (batch_id, aid, post.post_id, name, metric["value"], metric["unit"], metric["availability"]))
            db.execute("INSERT INTO audit(event,at,details) VALUES (?,?,?)",
                       ("ingest", datetime.now(timezone.utc).isoformat(), json.dumps({"batch": batch_id, "posts": len(posts)})))
        return {"inserted": True, "posts": len(posts), "digest": digest}

    def summary(self, now=None):
        now = now or datetime.now(timezone.utc)
        db = self.connection
        accounts = [dict(r) for r in db.execute("SELECT * FROM accounts ORDER BY id")]
        posts = []
        for row in db.execute("SELECT * FROM posts ORDER BY published_at,post_id"):
            item = dict(row)
            latest = db.execute("""SELECT b.id,b.observed_at FROM batches b JOIN metrics m ON m.batch_id=b.id
                WHERE m.account_id=? AND m.post_id=? ORDER BY b.observed_at DESC LIMIT 1""",
                (row["account_id"], row["post_id"])).fetchone()
            item["observed_at"] = latest["observed_at"]
            item["metrics"] = {m["name"]: {"value": m["value"], "unit": m["unit"], "availability": m["availability"]}
                               for m in db.execute("SELECT * FROM metrics WHERE batch_id=? AND post_id=?",
                                                   (latest["id"], row["post_id"]))}
            item["age_hours_at_observation"] = (aware_time(latest["observed_at"]) - aware_time(row["published_at"])).total_seconds() / 3600
            posts.append(item)
        last = db.execute("SELECT MAX(observed_at) FROM batches").fetchone()[0]
        totals = {}
        for key in ("views", "likes", "comments", "shares"):
            values = [p["metrics"][key]["value"] for p in posts if p["metrics"][key]["value"] is not None]
            totals[key] = {"observed_sum": sum(values) if values else None, "available_posts": len(values)}
        return {"accounts": accounts, "posts": posts, "totals": totals,
                "latest_observation": last,
                "freshness_seconds": max(0, (now - aware_time(last)).total_seconds()) if last else None,
                "batches": db.execute("SELECT COUNT(*) FROM batches").fetchone()[0],
                "prediction_status": "blocked: insufficient horizon-aligned TikTok observations",
                "monitoring_status": "manual authorized connector imports; no deployed poller"}

    def export(self):
        return {"schema": "s_ml.store-export.v1", "batches": [json.loads(r[0]) for r in
                self.connection.execute("SELECT payload FROM batches ORDER BY observed_at")]}

    def delete_account(self, account_id):
        with self.connection:
            self.connection.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            self.connection.execute("INSERT INTO audit(event,at,details) VALUES (?,?,?)",
                                    ("delete_account", datetime.now(timezone.utc).isoformat(), str(account_id)))
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.connection.execute("VACUUM")

    def backup(self, destination):
        with sqlite3.connect(destination) as target:
            self.connection.backup(target)

    def experiment(self, account_id, hypothesis, variable, metric, hours):
        if not hypothesis.strip() or not variable.strip() or metric not in ("views", "likes", "completion_rate"):
            raise ValueError("Specify hypothesis, independent variable and supported target metric")
        if not isinstance(hours, (int, float)) or not 0 < hours < 8760:
            raise ValueError("Observation window must be finite, positive and less than one year")
        with self.connection:
            cur = self.connection.execute("""INSERT INTO experiments
                (account_id,created_at,hypothesis,variable,target_metric,observation_hours,design)
                VALUES (?,?,?,?,?,?,?)""", (account_id, datetime.now(timezone.utc).isoformat(), hypothesis,
                variable, metric, hours, "observational; no random assignment or causal conclusion"))
        return cur.lastrowid
