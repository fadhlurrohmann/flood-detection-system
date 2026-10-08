"""
Local SQLite data logger for EFWS.

Data flow principle:
  read sensor → SAVE to the DB first (sensor_readings, the local source of truth)
              → try to send to the API
              → failed (no signal)? → goes into the queue (api_queue), the payload
                is stored AS-IS (exact JSON) so that when it is flushed
                again later the data does not change at all
              → EFWSPublisher re-checks the signal every EFWS_CONNECTIVITY_CHECK_SEC
                (default 2 minutes) and auto-flushes once it is back online.

Does NOT store any alarm_level / triggered_by / threshold — alarm &
threshold evaluation is now purely the backend's responsibility. The device only
evaluates the status LOCALLY (main.py) to sound the siren in
real time, without persisting it here.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta
from config import settings


class DBManager:
    def __init__(self, db_path: str = settings.DB_PATH):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    # ─── Schema ──────────────────────────────────────────────────
    def _init_tables(self):
        cur = self.conn.cursor()

        # Main table: one row per read cycle, one column per raw sensor value.
        # No status/alarm/threshold columns — that is the backend's job.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT    NOT NULL,
                device_id         TEXT    NOT NULL,

                water_current_ma  REAL,
                water_depth_m     REAL,
                water_fault_open  INTEGER,
                rainfall_mm       REAL,   -- accumulated rainfall since last reset/reading
                rain_working_hrs  REAL,   -- sensor's cumulative operating time

                full_payload      TEXT    -- the EXACT JSON sent to the API (for audit)
            )
        """)

        # Queue of failed API sends (offline buffer)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                endpoint    TEXT    NOT NULL,
                payload     TEXT    NOT NULL,
                attempts    INTEGER DEFAULT 0,
                last_error  TEXT,
                sent        INTEGER DEFAULT 0
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_queue_sent  ON api_queue(sent)")

        self.conn.commit()

    # ─── Logging sensor readings ──────────────────────────────────
    def log_reading(self, data: dict, api_payload: dict) -> int:
        """
        Save one read cycle to the database BEFORE it is attempted to be sent to the API.
        - data:        dict result of EFWS._read_all() → {"pressure":{...},
                       "rain":{...}}
        - api_payload: the EXACT payload that will be sent to the API, stored whole
                       in the full_payload column for audit/comparison with the contents of
                       the offline queue.
        Return: row id.
        """
        pressure = data.get("pressure", {})
        rain = data.get("rain", {})

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_readings (
                timestamp, device_id,
                water_current_ma, water_depth_m, water_fault_open,
                rainfall_mm, rain_working_hrs,
                full_payload
            ) VALUES (
                ?,?,  ?,?,?,  ?,?,  ?
            )
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,
            pressure.get("current_ma"), pressure.get("depth_m"),
            int(bool(pressure.get("fault_open_loop", False))),
            rain.get("rainfall_mm"), rain.get("working_time_hr"),
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── API queue (offline buffer) ───────────────────────────────
    def queue_api(self, endpoint: str, payload: dict):
        """Save the payload to the offline queue AS-IS (not modified/recomputed)."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO api_queue (timestamp, endpoint, payload)
            VALUES (?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            endpoint,
            json.dumps(payload, default=str),
        ))
        self.conn.commit()

    def get_pending_queue(self, limit: int = 20) -> list:
        """Fetch the queue items not yet sent (FIFO). Items that failed >10x are skipped (considered stale)."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, endpoint, payload, attempts
            FROM   api_queue
            WHERE  sent = 0 AND attempts < 10
            ORDER  BY id ASC
            LIMIT  ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def count_pending_queue(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM api_queue WHERE sent=0 AND attempts < 10")
        return cur.fetchone()[0]

    def mark_queue_sent(self, queue_id: int):
        self.conn.execute("UPDATE api_queue SET sent=1 WHERE id=?", (queue_id,))
        self.conn.commit()

    def mark_queue_failed(self, queue_id: int, error: str):
        self.conn.execute(
            "UPDATE api_queue SET attempts=attempts+1, last_error=? WHERE id=?",
            (error, queue_id)
        )
        self.conn.commit()

    # ─── Query helpers ────────────────────────────────────────────
    def recent_readings(self, limit: int = 20) -> list:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, timestamp,
                   water_depth_m, water_fault_open
            FROM   sensor_readings
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()

    # ─── Data retention (auto-cleanup) ────────────────────────────
    def purge_old_data(self, days: int = 3) -> dict:
        """
        Delete OLD rows (older than `days` days) from the local database.
        Called automatically by a background thread (main.py:
        EFWS._retention_loop). It does not delete the database file itself --
        only the old rows inside it, so recent data (<= `days` days)
        stays and the file size does not keep growing.

        - sensor_readings : every row older than the cutoff is deleted.
        - api_queue        : ONLY rows whose status is already "finished"
                              (sent=1, or attempts>=10 i.e. considered
                              permanently failed) are deleted. Items still
                              actively waiting for a retry are NOT deleted even if
                              they are older than `days` days, so no
                              data that has not yet been sent is lost.

        Return: {"sensor_readings_deleted": int, "api_queue_deleted": int}
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self.conn.cursor()

        cur.execute("DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff,))
        deleted_readings = cur.rowcount

        cur.execute(
            "DELETE FROM api_queue WHERE timestamp < ? AND (sent = 1 OR attempts >= 10)",
            (cutoff,),
        )
        deleted_queue = cur.rowcount

        self.conn.commit()
        if deleted_readings or deleted_queue:
            self.conn.execute("VACUUM")  # shrink the .db file size after deleting

        return {
            "sensor_readings_deleted": deleted_readings,
            "api_queue_deleted": deleted_queue,
        }
