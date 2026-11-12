"""Every column in the schema must be fillable. Catches name mismatches and forgotten sensors. Temp DB only."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EFWS_API_URL", "http://127.0.0.1:1/test")
from database.db_manager import DBManager
from config import settings

# one entry per sensor section, using the same names main.py uses; give every value a real, non-empty reading
DATA = {
    "bme":      {"temperature_c": 29.5, "humidity_percent": 63.0, "pressure_hpa": 1008.2},
    "pressure": {"current_ma": 8.2, "depth_m": 1.1, "pressure_bar": 0.1, "fault_open_loop": False},
    "wind":     {"speed_ms": 2.5},
    "wind_dir": {"direction_abbr": "NE"},
    "flow":     {"flow_lpm": 3.2, "total_liters": 10.5},
    "distance": {"distance_m": 0.87},
    "battery":  {"voltage": 12.1, "percent": 88.0},
    "rain":     {"rainfall_total_mm": 12.5, "rainfall_last_hour_mm": 0.4, "working_time_hours": 24},
    "aqi":      {"pm1": 6, "pm25": 8, "pm10": 11, "aqi": 26, "provisional": True},
}
PAYLOAD = {"telemetry": [{"rainfall": 0.7}]}
OK_TO_BE_EMPTY = {"sensor_errors"}               # only filled when a sensor fails


def main():
    previous_height = settings.ULTRASONIC_MOUNT_HEIGHT_M
    with tempfile.TemporaryDirectory() as directory:
        db = DBManager(db_path=os.path.join(directory, "t.db"))
        try:
            settings.ULTRASONIC_MOUNT_HEIGHT_M = 3.0
            rid = db.log_reading(DATA, PAYLOAD)
            row = dict(db.conn.execute("SELECT * FROM sensor_readings WHERE id=?", (rid,)).fetchone())
            empty = [name for name, value in row.items() if value is None and name not in OK_TO_BE_EMPTY]
            for name, value in row.items():
                print(f"  {'FAIL' if name in empty else 'ok  '} {name:24s} {value!r}")
            print("\nRESULT:", "ALL COLUMNS FILLED" if not empty else f"Empty columns: {empty}")
            return 1 if empty else 0
        finally:
            settings.ULTRASONIC_MOUNT_HEIGHT_M = previous_height
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
