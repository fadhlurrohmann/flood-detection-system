"""
SQLite local data logger untuk EFWS.

Prinsip alur data:
  baca sensor → SIMPAN ke DB dulu (sensor_readings, sumber kebenaran lokal)
              → coba kirim ke API
              → gagal (sinyal mati)? → masuk antrian (api_queue), payload
                disimpan APA ADANYA (JSON persis) supaya waktu di-flush
                ulang nanti datanya tidak berubah sedikit pun
              → EFWSPublisher cek sinyal ulang tiap EFWS_CONNECTIVITY_CHECK_SEC
                (default 2 menit) lalu auto flush kalau sudah online lagi.

TIDAK menyimpan alarm_level / triggered_by / threshold apa pun — evaluasi
alarm & threshold sekarang murni tanggung jawab backend. Device cuma
mengevaluasi status secara LOKAL (main.py) untuk menyalakan sirine secara
real-time, tanpa mempersistensikannya di sini.
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

        # Tabel utama: satu baris per siklus baca, kolom per sensor mentah.
        # Tidak ada kolom status/alarm/threshold — itu urusan backend.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           TEXT    NOT NULL,
                device_id           TEXT    NOT NULL,
                bme_temperature_c   REAL, 
                bme_humidity_pct    REAL,
                bme_pressure_hpa    REAL,
                wind_speed_ms       REAL,
                wind_direction      TEXT,
                sps_current_ma      REAL, 
                sps_depth_m         REAL,
                sps_pressure_bar    REAL, 
                sps_fault_open_loop INTEGER,
                flow_lpm            REAL,  
                distance_m          REAL,  
                battery_voltage     REAL,  
                battery_pct         REAL,
                rainfall_delta_mm   REAL,   -- mm sejak telemetry SEBELUMNYA (bukan window 1 jam)
                full_payload        TEXT    -- JSON PERSIS yang dikirim ke API (untuk audit)
            )
        """)

        # Antrian pengiriman API yang gagal (offline buffer)
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

        # Log setiap kali Location Publisher MENCOBA kirim (bukan cuma yang
        # sukses -- kalau gagal & masuk api_queue, baris ini tetap ada,
        # supaya riwayat "device pernah lapor posisi X pada waktu Y" tidak
        # hilang, terpisah dari mekanisme retry queue).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS location_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                device_id   TEXT    NOT NULL,
                latitude    REAL,
                longitude   REAL,
                source      TEXT,     -- "gps" atau "config" (fallback)
                fix         INTEGER,  -- 1 kalau GPS benar-benar fix, 0 kalau fallback
                full_payload TEXT     -- JSON PERSIS yang dikirim ke API (untuk audit)
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_queue_sent  ON api_queue(sent)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_location_ts ON location_log(timestamp)")

        self.conn.commit()

    # ─── Logging sensor readings ──────────────────────────────────
    def log_reading(self, data: dict, api_payload: dict) -> int:
        """
        Simpan satu siklus baca ke database SEBELUM dicoba dikirim ke API.
        - data:        dict hasil EFWS._read_all() → {"mq2":{...}, "mq135":{...},
                       "bme280":{...}, "soil":{"surface":{...},"deep":{...}},
                       "wind":{...}, "pressure":{...}, "battery":{...}}
        - api_payload: payload PERSIS yang akan dikirim ke API, disimpan utuh
                       di kolom full_payload untuk audit/pembanding dengan isi
                       antrian offline. Kolom rainfall_delta_mm diambil dari
                       SINI (bukan dihitung ulang dari data mentah), supaya
                       nilainya PERSIS sama dengan yang benar-benar dikirim
                       (main.py EFWS._rainfall_delta() adalah sumber kebenaran
                       satu-satunya untuk nilai delta ini).
        Return: row id.
        """
        bme        = data.get("bme_sensor", {})
        sps        = data.get("sps_sensor", {})
        wind_speed = data.get("wind_speed_sensor", {})
        wind_dir   = data.get("wind_dir_sensor", {})
        flow       = data.get("flow_sensor", {})
        distance   = data.get("distance_sensor", {})
        battery    = data.get("battery_sensor", {})
        rainfall_delta_mm = None
        
        try:
            rainfall_delta_mm = api_payload["telemetry"][0].get("rainfall")
        except (KeyError, IndexError, TypeError):
            pass

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sensor_readings (
                timestamp, device_id,
                bme_temperature_c, bme_humidity_pct, bme_pressure_hpa,
                wind_speed_ms, wind_direction,
                sps_current_ma, sps_depth_m, sps_pressure_bar, sps_fault_open_loop,
                flow_lpm,
                distance_m,
                battery_voltage, battery_pct,
                rainfall_delta_mm,
                full_payload
            ) VALUES (
                ?,?,  ?,?,?,  ?,?,  ?,?,?,?,  ?,  ?,  ?,?,  ?,  ?
            )
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,
            bme.get("temperature_c"), bme.get("humidity_percent"), bme.get("pressure_hpa"),
            wind_speed.get("speed_ms"), wind_dir.get("direction_abbr"),
            sps.get("current_ma"), sps.get("depth_m"), sps.get("pressure_bar"), int(bool(sps.get("fault_open_loop", False))),
            flow.get("flow_lpm"),
            distance.get("distance_m"),
            battery.get("voltage"), battery.get("percent"),
            rainfall_delta_mm,
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── Logging location (Location Publisher) ────────────────────
    def log_location(self, location: dict, api_payload: dict) -> int:
        """
        Simpan setiap kali Location Publisher MENCOBA kirim -- terlepas dari
        sukses/gagalnya pengiriman (kalau gagal, tetap tercatat di sini DAN
        masuk api_queue lewat mekanisme retry terpisah).
        - location:    dict {"lat", "lon", "source", "fix"} (self._location
                       milik EFWS di main.py).
        - api_payload: payload PERSIS yang dikirim ke API (untuk audit).
        Return: row id.
        """
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO location_log (
                timestamp, device_id, latitude, longitude, source, fix, full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            settings.DEVICE_ID,
            location.get("lat"),
            location.get("lon"),
            location.get("source"),
            int(bool(location.get("fix", False))),
            json.dumps(api_payload, default=str),
        ))
        self.conn.commit()
        return cur.lastrowid

    # ─── API queue (offline buffer) ───────────────────────────────
    def queue_api(self, endpoint: str, payload: dict):
        """Simpan payload ke antrian offline APA ADANYA (tidak diubah/dihitung ulang)."""
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
        """Ambil antrian yang belum terkirim (FIFO). Item gagal >10x dilewati (dianggap stale)."""
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
            SELECT  timestamp, device_id,
                    bme_temperature_c, bme_humidity_pct, bme_pressure_hpa,
                    wind_speed_ms, wind_direction,
                    sps_current_ma, sps_depth_m, sps_pressure_bar, sps_fault_open_loop,
                    flow_lpm,
                    distance_m,
                    battery_voltage, battery_pct,
                    rainfall_delta_mm
            FROM   sensor_readings
            ORDER  BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()

    # ─── Retensi data (auto-cleanup) ──────────────────────────────
    def purge_old_data(self, days: int = 3) -> dict:
        """
        Hapus baris LAMA (lebih tua dari `days` hari) dari database lokal.
        Dipanggil otomatis oleh background thread (main.py:
        EFWS._retention_loop), bukan menghapus file database-nya sendiri --
        cuma baris lama di dalamnya, supaya data terbaru (<= `days` hari)
        tetap ada dan ukuran file tidak terus membengkak.

        - sensor_readings : semua baris lebih tua dari cutoff dihapus.
        - api_queue        : HANYA baris yang statusnya sudah "selesai"
                              (sent=1, atau attempts>=10 alias dianggap
                              gagal permanen) yang dihapus. Item yang masih
                              aktif menunggu retry TIDAK dihapus meskipun
                              usianya lebih dari `days` hari, supaya tidak
                              kehilangan data yang belum sempat terkirim.

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

        cur.execute("DELETE FROM location_log WHERE timestamp < ?", (cutoff,))
        deleted_location = cur.rowcount

        self.conn.commit()
        if deleted_readings or deleted_queue or deleted_location:
            self.conn.execute("VACUUM")  # kecilkan ukuran file .db setelah hapus

        return {
            "sensor_readings_deleted": deleted_readings,
            "api_queue_deleted": deleted_queue,
            "location_log_deleted": deleted_location,
        }