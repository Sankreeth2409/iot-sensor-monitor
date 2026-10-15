"""SQLite storage (standard library). All queries are parameterised."""
from __future__ import annotations

import sqlite3
import threading

from .anomaly import Alert
from .schema import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT NOT NULL, metric TEXT NOT NULL,
  value REAL NOT NULL, unit TEXT NOT NULL, ts REAL NOT NULL, seq INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_readings ON readings(device, metric, id);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, device TEXT NOT NULL, metric TEXT NOT NULL,
  kind TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL, value REAL);
"""


class Store:
    def __init__(self, path=":memory:"):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            if path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)

    def add_reading(self, r: Reading):
        with self._lock:
            self._db.execute("INSERT INTO readings(device,metric,value,unit,ts,seq) VALUES (?,?,?,?,?,?)",
                             (r.device, r.metric, r.value, r.unit, r.ts, r.seq))
            self._db.commit()

    def add_alert(self, a: Alert):
        with self._lock:
            self._db.execute("INSERT INTO alerts(ts,device,metric,kind,severity,message,value) VALUES (?,?,?,?,?,?,?)",
                             (a.ts, a.device, a.metric, a.kind, a.severity, a.message, a.value))
            self._db.commit()

    def _rows(self, sql, args=()):
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def latest(self):
        return self._rows("""SELECT r.device, r.metric, r.value, r.unit, r.ts FROM readings r
                             JOIN (SELECT MAX(id) mid FROM readings GROUP BY device, metric) m ON r.id = m.mid
                             ORDER BY r.device, r.metric""")

    def series(self, device, metric, limit=200):
        rows = self._rows("SELECT ts, value FROM readings WHERE device=? AND metric=? ORDER BY id DESC LIMIT ?",
                          (device, metric, limit))
        return rows[::-1]

    def alerts(self, limit=50):
        return self._rows("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))

    def all_alerts(self):
        return self._rows("SELECT * FROM alerts ORDER BY id")

    def counts(self):
        with self._lock:
            n_r = self._db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            n_a = self._db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            n_s = self._db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM readings GROUP BY device, metric)").fetchone()[0]
        return {"readings": n_r, "alerts": n_a, "series": n_s}

    def close(self):
        with self._lock:
            self._db.close()

    def __del__(self):
        try:
            self._db.close()
        except Exception:
            pass
