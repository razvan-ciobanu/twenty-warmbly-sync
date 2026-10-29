"""SQLite state: record links with their last synced snapshot, received events, a job queue.

links      one row per Twenty record (person/company) and its Warmbly contact; snapshot is
           the field values both sides agreed on at the last sync (JSON). active = 0 while
           the Twenty record is deleted or has no email.
events     webhook event ids already accepted (exactly-once).
jobs       work for the single worker thread; a pending job's key is unique, so repeated
           webhooks for one record collapse into one sync.
errors     the current problem per record (e.g. an email collision), shown in metrics.
meta       reconciliation cursors and timestamps.
"""
import json
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    twenty_kind TEXT NOT NULL,
    twenty_id   TEXT NOT NULL,
    warmbly_id  TEXT NOT NULL UNIQUE,
    snapshot    TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    synced_at   REAL NOT NULL,
    PRIMARY KEY (twenty_kind, twenty_id)
);
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    received_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY,
    key        TEXT NOT NULL,
    kind       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    next_at    REAL NOT NULL,
    done_at    REAL,
    last_error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_pending_key ON jobs(key) WHERE done_at IS NULL;
CREATE TABLE IF NOT EXISTS errors (
    key     TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
"""

MAX_BACKOFF = 3600


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=30, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        """One write transaction (the connection is in autocommit mode otherwise)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # links
    def link_by_twenty(self, kind, twenty_id):
        return self._link("twenty_kind = ? AND twenty_id = ?", kind, twenty_id)

    def link_by_warmbly(self, warmbly_id):
        return self._link("warmbly_id = ?", warmbly_id)

    def _link(self, where, *args):
        row = self.db.execute(f"SELECT * FROM links WHERE {where}", args).fetchone()
        if row is None:
            return None
        link = dict(row)
        link["snapshot"] = json.loads(link["snapshot"])
        return link

    def save_link(self, kind, twenty_id, warmbly_id, snapshot, active=True):
        with self.tx():
            self.db.execute("DELETE FROM links WHERE warmbly_id = ? AND NOT (twenty_kind = ? AND twenty_id = ?)",
                            (warmbly_id, kind, twenty_id))
            self.db.execute(
                "INSERT INTO links (twenty_kind, twenty_id, warmbly_id, snapshot, active, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (twenty_kind, twenty_id) DO UPDATE SET "
                "warmbly_id = excluded.warmbly_id, snapshot = excluded.snapshot, "
                "active = excluded.active, synced_at = excluded.synced_at",
                (kind, twenty_id, warmbly_id, json.dumps(snapshot, sort_keys=True), int(active), time.time()))

    def set_active(self, kind, twenty_id, active):
        self.db.execute("UPDATE links SET active = ? WHERE twenty_kind = ? AND twenty_id = ?",
                        (int(active), kind, twenty_id))

    def links(self):
        for row in self.db.execute("SELECT * FROM links").fetchall():
            link = dict(row)
            link["snapshot"] = json.loads(link["snapshot"])
            yield link

    # events + jobs
    def accept_event(self, event_id, source, jobs):
        """Record a webhook event and enqueue its jobs atomically; False if already seen."""
        with self.tx():
            cur = self.db.execute("INSERT OR IGNORE INTO events (event_id, source, received_at) VALUES (?, ?, ?)",
                                  (event_id, source, time.time()))
            if cur.rowcount == 0:
                return False
            for key, kind, payload in jobs:
                self._enqueue(key, kind, payload)
        return True

    def enqueue(self, key, kind, payload=None, delay=0):
        with self.tx():
            self._enqueue(key, kind, payload, delay)

    def _enqueue(self, key, kind, payload=None, delay=0):
        self.db.execute(
            "INSERT INTO jobs (key, kind, payload, next_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (key) WHERE done_at IS NULL DO UPDATE SET next_at = MIN(next_at, excluded.next_at)",
            (key, kind, json.dumps(payload or {}), time.time() + delay))

    def next_job(self, now=None):
        row = self.db.execute("SELECT * FROM jobs WHERE done_at IS NULL AND next_at <= ? ORDER BY next_at, id LIMIT 1",
                              (now or time.time(),)).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        return job

    def update_payload(self, job_id, payload):
        self.db.execute("UPDATE jobs SET payload = ? WHERE id = ?", (json.dumps(payload), job_id))

    def finish(self, job_id):
        self.db.execute("UPDATE jobs SET done_at = ?, last_error = NULL WHERE id = ?", (time.time(), job_id))

    def fail(self, job_id, attempts, error):
        backoff = min(MAX_BACKOFF, 30 * 2 ** attempts)
        self.db.execute("UPDATE jobs SET attempts = ?, next_at = ?, last_error = ? WHERE id = ?",
                        (attempts + 1, time.time() + backoff, error[:1000], job_id))

    def prune(self, older_than_days=30):
        cutoff = time.time() - older_than_days * 86400
        with self.tx():
            self.db.execute("DELETE FROM jobs WHERE done_at < ?", (cutoff,))
            self.db.execute("DELETE FROM events WHERE received_at < ?", (cutoff,))

    # errors + meta
    def set_error(self, key, message):
        self.db.execute("INSERT INTO errors (key, message, at) VALUES (?, ?, ?) ON CONFLICT (key) DO UPDATE SET "
                        "message = excluded.message, at = excluded.at", (key, message, time.time()))

    def clear_error(self, key):
        self.db.execute("DELETE FROM errors WHERE key = ?", (key,))

    def get_meta(self, k, default=None):
        row = self.db.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return row["v"] if row else default

    def set_meta(self, k, v):
        self.db.execute("INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT (k) DO UPDATE SET v = excluded.v",
                        (k, str(v)))

    def stats(self):
        q = self.db.execute
        return {
            "pending_jobs": q("SELECT count(*) FROM jobs WHERE done_at IS NULL").fetchone()[0],
            "failing_jobs": q("SELECT count(*) FROM jobs WHERE done_at IS NULL AND attempts > 0").fetchone()[0],
            "errors": q("SELECT count(*) FROM errors").fetchone()[0],
            "links": q("SELECT count(*) FROM links WHERE active = 1").fetchone()[0],
        }
