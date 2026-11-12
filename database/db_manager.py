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
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps

from config import settings


def _locked(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class DBManager:
    def __init__(self, db_path=None):
        db_path = settings.DB_PATH if db_path is None else db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
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

        # Additive migration preserves historical rows, including legacy columns.
        columns = {row[1] for row in cur.execute("PRAGMA table_info(sensor_readings)")}
        for name in (
            "water_current_ma", "water_depth_m", "rainfall_mm", "rain_working_hrs",
            "water_pressure_bar", "distance_m", "ultrasonic_depth_m",
            "flow_lpm", "flow_total_liters", "rainfall_total_mm",
            "rainfall_last_hour_mm", "battery_voltage", "battery_percent",
            "bme_temperature_c", "bme_humidity_pct", "bme_pressure_hpa", "wind_speed_ms",
            "sps_current_ma", "sps_depth_m", "sps_pressure_bar", "battery_pct", "rainfall_delta_mm",
            "aqi_pm1", "aqi_pm25", "aqi_pm10", "aqi",
        ):
            if name not in columns:
                cur.execute(f"ALTER TABLE sensor_readings ADD COLUMN {name} REAL")
        if "sensor_errors" not in columns:
            cur.execute("ALTER TABLE sensor_readings ADD COLUMN sensor_errors TEXT")
        for name, column_type in {"water_fault_open": "INTEGER", "sps_fault_open_loop": "INTEGER",
                                  "wind_direction": "TEXT", "aqi_provisional": "INTEGER"}.items():
            if name not in columns:
                cur.execute(f"ALTER TABLE sensor_readings ADD COLUMN {name} {column_type}")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS location_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                device_id TEXT NOT NULL, latitude REAL, longitude REAL,
                source TEXT, fix INTEGER, full_payload TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_location_ts ON location_log(timestamp)")
        cur.execute("CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value REAL)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_queue_sent  ON api_queue(sent)")

        self.conn.commit()

    # ─── Logging sensor readings ──────────────────────────────────
    @_locked
    def log_reading(self, data: dict, api_payload: dict) -> int:
        """Store all sensor values and the exact payload without dropping legacy columns."""
        pressure = data.get("pressure", {})
        rain = data.get("rain", {})
        flow = data.get("flow", {})
        battery = data.get("battery", {})
        bme = data.get("bme", {})
        wind = data.get("wind", {})
        direction = data.get("wind_dir", {})
        air = data.get("aqi", {})
        distance = data.get("distance", {}).get("distance_m")
        height = settings.ULTRASONIC_MOUNT_HEIGHT_M
        ultrasonic_depth = round(height - distance, 3) if (
            height is not None and distance is not None and 0 <= distance <= height
        ) else None
        fault = pressure.get("fault_open_loop")
        fault = int(fault) if fault is not None else None
        errors = {name: reading["error"] for name, reading in data.items()
                  if isinstance(reading, dict) and reading.get("error")}
        record = {
            "timestamp": data.get("_timestamp", datetime.now(timezone.utc).isoformat()),
            "device_id": settings.DEVICE_ID,
            "water_current_ma": pressure.get("current_ma"),
            "water_depth_m": pressure.get("depth_m"),
            "water_fault_open": fault,
            "water_pressure_bar": pressure.get("pressure_bar"),
            "rainfall_mm": rain.get("rainfall_last_hour_mm"),
            "rain_working_hrs": rain.get("working_time_hours"),
            "distance_m": distance, "ultrasonic_depth_m": ultrasonic_depth,
            "flow_lpm": flow.get("flow_lpm"), "flow_total_liters": flow.get("total_liters"),
            "rainfall_total_mm": rain.get("rainfall_total_mm"),
            "rainfall_last_hour_mm": rain.get("rainfall_last_hour_mm"),
            "battery_voltage": battery.get("voltage"), "battery_percent": battery.get("percent"),
            "bme_temperature_c": bme.get("temperature_c"),
            "bme_humidity_pct": bme.get("humidity_percent"),
            "bme_pressure_hpa": bme.get("pressure_hpa"),
            "wind_speed_ms": wind.get("speed_ms"), "wind_direction": direction.get("direction_abbr"),
            "sps_current_ma": pressure.get("current_ma"), "sps_depth_m": pressure.get("depth_m"),
            "sps_pressure_bar": pressure.get("pressure_bar"), "sps_fault_open_loop": fault,
            "battery_pct": battery.get("percent"),
            "rainfall_delta_mm": api_payload["telemetry"][0].get("rainfall"),
            "aqi_pm1": air.get("pm1"), "aqi_pm25": air.get("pm25"),
            "aqi_pm10": air.get("pm10"), "aqi": air.get("aqi"),
            "aqi_provisional": int(air["provisional"]) if air.get("provisional") is not None else None,
            "full_payload": json.dumps(api_payload, allow_nan=False),
            "sensor_errors": json.dumps(errors),
        }
        placeholders = ", ".join("?" for _ in record)
        with self.conn:
            cur = self.conn.execute(
                f"INSERT INTO sensor_readings ({', '.join(record)}) VALUES ({placeholders})",
                tuple(record.values()),
            )
        return cur.lastrowid

    # ─── API queue (offline buffer) ───────────────────────────────
    @_locked
    def queue_api(self, endpoint: str, payload: dict):
        """Save the payload to the offline queue AS-IS (not modified/recomputed)."""
        self.queue_bundle([(endpoint, payload)])

    @_locked
    def queue_bundle(self, payloads, rainfall_total_mm=None, device_id=None):
        """Atomically persist an entire upload bundle before any network request."""
        timestamp = datetime.now(timezone.utc).isoformat()
        rows = [(timestamp, endpoint, json.dumps(payload, allow_nan=False))
                for endpoint, payload in payloads]
        with self.conn:
            self.conn.executemany(
                "INSERT INTO api_queue (timestamp, endpoint, payload) VALUES (?, ?, ?)", rows
            )
            if rainfall_total_mm is not None and device_id is not None:
                self.conn.execute("INSERT OR REPLACE INTO runtime_state (key, value) VALUES (?, ?)",
                                  (f"rainfall_total:{device_id}", rainfall_total_mm))

    @_locked
    def get_rainfall_baseline(self, device_id):
        row = self.conn.execute("SELECT value FROM runtime_state WHERE key=?",
                                (f"rainfall_total:{device_id}",)).fetchone()
        return row[0] if row is not None else None

    @_locked
    def log_location(self, location, api_payload):
        with self.conn:
            cur = self.conn.execute("""
                INSERT INTO location_log
                (timestamp, device_id, latitude, longitude, source, fix, full_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (datetime.now(timezone.utc).isoformat(), settings.DEVICE_ID,
                  location.get("lat"), location.get("lon"), location.get("source"),
                  int(bool(location.get("fix"))), json.dumps(api_payload, allow_nan=False)))
        return cur.lastrowid

    @_locked
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

    @_locked
    def count_pending_queue(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM api_queue WHERE sent=0 AND attempts < 10")
        return cur.fetchone()[0]

    @_locked
    def mark_queue_sent(self, queue_id: int):
        self.conn.execute("UPDATE api_queue SET sent=1 WHERE id=?", (queue_id,))
        self.conn.commit()

    @_locked
    def mark_queue_failed(self, queue_id: int, error: str):
        self.conn.execute(
            "UPDATE api_queue SET attempts=attempts+1, last_error=? WHERE id=?",
            (error, queue_id)
        )
        self.conn.commit()

    @_locked
    def mark_queue_discarded(self, queue_id: int, error: str):
        self.conn.execute("UPDATE api_queue SET sent=-1, last_error=? WHERE id=?", (error, queue_id))
        self.conn.commit()

    # ─── Query helpers ────────────────────────────────────────────
    @_locked
    def recent_readings(self, limit: int = 20) -> list:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, timestamp,
                   water_depth_m, water_fault_open, distance_m, flow_lpm,
                   rainfall_last_hour_mm, battery_voltage, sensor_errors,
                   bme_temperature_c, bme_humidity_pct, bme_pressure_hpa,
                   wind_speed_ms, wind_direction, sps_current_ma, sps_depth_m,
                   sps_pressure_bar, sps_fault_open_loop, battery_pct, rainfall_delta_mm,
                   aqi_pm1, aqi_pm25, aqi_pm10, aqi, aqi_provisional
            FROM   sensor_readings
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    @_locked
    def close(self):
        self.conn.close()

    # ─── Data retention (auto-cleanup) ────────────────────────────
    @_locked
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
            "DELETE FROM api_queue WHERE timestamp < ? AND (sent != 0 OR attempts >= 10)",
            (cutoff,),
        )
        deleted_queue = cur.rowcount

        cur.execute("DELETE FROM location_log WHERE timestamp < ?", (cutoff,))
        deleted_location = cur.rowcount

        self.conn.commit()

        return {
            "sensor_readings_deleted": deleted_readings,
            "api_queue_deleted": deleted_queue,
            "location_log_deleted": deleted_location,
        }
