"""
SQLite local data logger for EFWS.

Prinsip alur data:
  read sensors → SAVE ke DB dulu (sensor_readings, sumber kebenaran local)
              → coba send ke API
              → failed (signal mati)? → enter queue (api_queue), payload
                disimpan APA ADANYA (JSON persis) so that waktu di-flush
                again nanti datanya not berubah sedikit pun
              → EFWSPublisher check signal again every EFWS_CONNECTIVITY_CHECK_SEC
                (default 2 minutes) lalu auto flush if sudah online lagi.

TIDAK menyimpan alarm_level / triggered_by / threshold apa pun — evaluasi
alarm & threshold sekarang murni tanggung jawab backend. Device only
mengevaluasi status secara LOCAL (main.py) for menyalakan sirine secara
real-time, without mempersistensikannya di sini.
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

        # Tabel main: satu rows per read cycle, columns per sensor raw.
        # None columns status/alarm/threshold — itu urusan backend.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT    NOT NULL,
                device_id         TEXT    NOT NULL,

                soil_surface_pct  REAL,
                soil_deep_pct     REAL,
                water_current_ma  REAL,
                water_depth_m     REAL,
                water_fault_open  INTEGER,
                rainfall_mm       REAL,   -- accumulated rainfall since last reset/reading
                rain_working_hrs  REAL,   -- sensor's cumulative operating time

                full_payload      TEXT    -- JSON PERSIS that sent ke API (for audit)
            )
        """)

        # Queue API delivery that failed (offline buffer)
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
        Save satu read cycle ke database BEFORE dicoba sent ke API.
        - data:        dict result EFWS._read_all() → {"soil":{"surface":{...},
                       "deep":{...}}, "pressure":{...}}
        - api_payload: payload PERSIS that akan sent ke API, disimpan utuh
                       di columns full_payload for audit/pembanding with content
                       offline queue.
        Return: row id.
        """
        soil     = data.get("soil", {})
        pressure = data.get("pressure", {})
        rain = data.get("rain", {})

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_readings (
                timestamp, device_id,
                soil_surface_pct, soil_deep_pct,
                water_current_ma, water_depth_m, water_fault_open,
                rainfall_mm, rain_working_hrs,
                full_payload
            ) VALUES (
                ?,?,  ?,?,  ?,?,?,  ?,?,  ?
            )
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,
            soil.get("surface", {}).get("moisture_percent"),
            soil.get("deep", {}).get("moisture_percent"),
            pressure.get("current_ma"), pressure.get("depth_m"),
            int(bool(pressure.get("fault_open_loop", False))),
            rain.get("rainfall_mm"), rain.get("working_time_hr"),
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── API queue (offline buffer) ───────────────────────────────
    def queue_api(self, endpoint: str, payload: dict):
        """Save payload ke offline queue APA ADANYA (not diubah/dihitung again)."""
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
        """Get queue that belum sent (FIFO). Item failed >10x dilewati (dianggap stale)."""
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
                   soil_surface_pct, soil_deep_pct,
                   water_depth_m, water_fault_open
            FROM   sensor_readings
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()

    # ─── Retention data (auto-cleanup) ──────────────────────────────
    def purge_old_data(self, days: int = 3) -> dict:
        """
        Delete rows LAMA (lebih tua from `days` days) from local database.
        Dipanggil otomatis oleh background thread (main.py:
        EFWS._retention_loop), not menghapus file database-nya sendiri --
        only rows old di dalamnya, so that data terbaru (<= `days` days)
        tetap ada dan ukuran file not terus membengkak.

        - sensor_readings : all rows lebih tua from cutoff dihapus.
        - api_queue        : ONLY rows that statusnya sudah "complete"
                              (sent=1, or attempts>=10 alias dianggap
                              failed permanen) that dihapus. Item that masih
                              aktif menunggu retry TIDAK dihapus meskipun
                              usianya lebih from `days` days, so that not
                              kehilangan data that belum sempat sent.

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
            self.conn.execute("VACUUM")  # kecilkan ukuran file .db after delete

        return {
            "sensor_readings_deleted": deleted_readings,
            "api_queue_deleted": deleted_queue,
        }